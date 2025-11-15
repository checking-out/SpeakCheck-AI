import subprocess
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

import boto3
import whisper
from botocore.exceptions import ClientError
import yt_dlp
import requests

from config import Settings
from database import Database
from question_generator import QuestionGenerator
from pdf_to_text import PDFTextExtractor
from pdf_ocr import PDFOCR

_MODEL_CACHE: Dict[str, Any] = {}
_PDF_TEXT_EXTRACTOR = PDFTextExtractor()
_PDF_OCR = PDFOCR()


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_temp_artifacts(allowed_roots: List[Path], *paths: Optional[Path]) -> None:
    for candidate in paths:
        if not candidate:
            continue
        try:
            resolved = candidate.resolve()
        except FileNotFoundError:
            continue

        should_delete = False
        for root in allowed_roots:
            try:
                if resolved.is_relative_to(root):
                    should_delete = True
                    break
            except AttributeError:
                # Python < 3.9 fallback
                try:
                    resolved.relative_to(root)
                    should_delete = True
                    break
                except ValueError:
                    continue

        if should_delete:
            try:
                resolved.unlink(missing_ok=True)
                print(f"🧹 임시 파일 삭제: {resolved}")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"⚠️  임시 파일 삭제 실패 ({resolved}): {exc}")


def download_video_from_web(url: str, download_dir: Path, job_id: int) -> Path:
    ensure_directory(download_dir)
    output_template = download_dir / f"{job_id}_%(title)s.%(ext)s"
    ydl_opts = {
        "outtmpl": str(output_template),
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            downloaded_path = Path(ydl.prepare_filename(info))
            print(f"⬇️  웹에서 비디오 다운로드 완료: {downloaded_path}")
            return downloaded_path
    except Exception as exc:  # pylint: disable=broad-except
        print(f"⚠️  yt-dlp 다운로드 실패, HTTP 다운로드 시도: {exc}")

    fallback_path = download_dir / f"{job_id}_video"
    try:
        return download_file_via_http(url, fallback_path, suffix=".mp4")
    except Exception as http_exc:  # pylint: disable=broad-except
        raise RuntimeError(f"웹 비디오 다운로드 실패: {http_exc}") from http_exc


def download_file_via_http(url: str, base_path: Path, suffix: Optional[str] = None) -> Path:
    target_path = base_path
    if suffix:
        target_path = base_path.with_suffix(suffix)
    else:
        target_path = Path(base_path)
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()

    with open(target_path, "wb") as file_handle:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                file_handle.write(chunk)

    print(f"⬇️  HTTP 다운로드 완료: {target_path}")
    return target_path


def get_whisper_model(model_size: str) -> Any:
    if model_size not in _MODEL_CACHE:
        print(f"🔄 Whisper 모델 로딩 중: {model_size}")
        _MODEL_CACHE[model_size] = whisper.load_model(model_size)
    return _MODEL_CACHE[model_size]


def extract_audio_from_video(video_path: Path, output_dir: Path) -> Path:
    ensure_directory(output_dir)
    base_name = video_path.stem
    output_path = output_dir / f"{base_name}.mp3"

    if not output_path.exists():
        command = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",
            "-acodec",
            "mp3",
            "-ab",
            "192k",
            "-ar",
            "44100",
            str(output_path),
        ]
        subprocess.run(command, check=True)

    return output_path


def transcribe_audio(audiofile: Path, model_size: str = "medium", language: Optional[str] = None) -> Dict[str, Any]:
    model = get_whisper_model(model_size)

    transcribe_options: Dict[str, Any] = {
        "fp16": False,
        "verbose": True,
        "word_timestamps": True,
        "condition_on_previous_text": True,
        "compression_ratio_threshold": 2.4,
        "logprob_threshold": -1.0,
        "no_speech_threshold": 0.6,
    }

    if language:
        transcribe_options["language"] = language

    return model.transcribe(str(audiofile), **transcribe_options)


def analyze_transcription_quality(result: Dict[str, Any], verbose: bool = True) -> Dict[str, Any]:
    text = result.get("text", "")
    segments = result.get("segments", [])

    word_count = len(text.split())
    char_count = len(text)
    segment_count = len(segments)

    avg_prob = 0.0
    low_confidence_segments = []
    if segment_count:
        avg_prob = sum(seg.get("avg_logprob", 0.0) for seg in segments) / segment_count
        low_confidence_segments = [
            {
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", "").strip(),
                "avg_logprob": seg.get("avg_logprob"),
            }
            for seg in segments
            if seg.get("avg_logprob", 0.0) < -1.0
        ]

    quality_report = {
        "word_count": word_count,
        "char_count": char_count,
        "segment_count": segment_count,
        "avg_confidence": avg_prob,
        "low_confidence_segments_count": len(low_confidence_segments),
    }

    if verbose:
        print("\n" + "=" * 50)
        print("📊 변환 품질 분석")
        print("=" * 50)
        print(f"📝 총 단어 수: {word_count}")
        print(f"📝 총 문자 수: {char_count}")
        print(f"📝 구간 수: {segment_count}")
        print(f"📊 평균 신뢰도: {avg_prob:.2f}")

        if low_confidence_segments:
            print(f"⚠️  낮은 신뢰도 구간: {len(low_confidence_segments)}개")
            for seg in low_confidence_segments[:3]:
                print(
                    f"   {seg['start']:.1f}s-{seg['end']:.1f}s: "
                    f"{seg['text'][:50]}{'...' if len(seg['text']) > 50 else ''}"
                )

        print("\n💡 개선 제안:")
        if avg_prob < -0.5:
            print("   • 발음이 불분명할 수 있습니다. 더 큰 모델을 사용해보세요 (large)")
            print("   • 배경 소음이 있을 수 있습니다. 조용한 환경에서 녹음해보세요")
        if word_count < 10:
            print("   • 텍스트가 너무 짧습니다. 더 긴 오디오를 사용해보세요")
        if segment_count > 50:
            print("   • 구간이 너무 많습니다. 연속적인 발화를 시도해보세요")

    return quality_report


def resolve_video_source(
    job: Dict[str, Any],
    settings: Settings,
    s3_client: Any,
) -> Path:
    video_source = job["video_source"]
    potential_path = Path(video_source).expanduser()
    if potential_path.exists():
        return potential_path

    ensure_directory(Path(settings.downloads_dir))

    if video_source.startswith(("http://", "https://")):
        return download_video_from_web(video_source, Path(settings.downloads_dir), job["id"])

    if video_source.startswith("s3://"):
        _, _, remainder = video_source.partition("s3://")
        bucket, _, key = remainder.partition("/")
        if not bucket or not key:
            raise ValueError(f"잘못된 S3 경로입니다: {video_source}")
    else:
        bucket = settings.aws_bucket
        key = video_source.lstrip("/")

    local_name = f"{job['id']}_{Path(key).name}"
    local_path = Path(settings.downloads_dir) / local_name

    if not local_path.exists():
        print(f"⬇️  S3에서 비디오 다운로드 중: s3://{bucket}/{key}")
        try:
            s3_client.download_file(bucket, key, str(local_path))
        except ClientError as exc:
            raise RuntimeError(f"S3 다운로드 실패: {exc}") from exc

    return local_path


def resolve_document_source(
    speech: Dict[str, Any],
    settings: Settings,
    s3_client: Any,
) -> Optional[Path]:
    document_url = speech.get("document_url")
    if not document_url:
        return None

    potential_path = Path(str(document_url)).expanduser()
    if potential_path.exists():
        return potential_path

    ensure_directory(Path(settings.downloads_dir))

    if str(document_url).startswith(("http://", "https://")):
        return download_document_from_web(str(document_url), Path(settings.downloads_dir), speech["id"])

    if document_url.startswith("s3://"):
        _, _, remainder = document_url.partition("s3://")
        bucket, _, key = remainder.partition("/")
        if not bucket or not key:
            raise ValueError(f"잘못된 S3 경로입니다: {document_url}")
    else:
        bucket = settings.aws_bucket
        key = document_url.lstrip("/")

    local_name = f"{speech['id']}_{Path(key).name}"
    local_path = Path(settings.downloads_dir) / local_name

    if not local_path.exists():
        print(f"⬇️  S3에서 문서 다운로드 중: s3://{bucket}/{key}")
        try:
            s3_client.download_file(bucket, key, str(local_path))
        except ClientError as exc:
            raise RuntimeError(f"S3 문서 다운로드 실패: {exc}") from exc

    return local_path


def download_document_from_web(url: str, download_dir: Path, speech_id: UUID) -> Optional[Path]:
    ensure_directory(download_dir)
    suffix = Path(url).suffix.lower()
    if suffix not in {".pdf", ".ppt", ".pptx"}:
        print(f"⚠️  지원하지 않는 문서 형식입니다: {url}")
        return None

    filename = f"{speech_id}_document{suffix}"
    target_path = download_dir / filename
    try:
        return download_file_via_http(url, target_path)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"⚠️  문서 다운로드 실패: {exc}")
        return None


def extract_document_text(document_path: Path) -> Dict[str, Any]:
    primary = _PDF_TEXT_EXTRACTOR.extract_text(str(document_path))
    if primary.get("success") and primary.get("full_text"):
        return {
            "method": primary.get("method", "pdfplumber"),
            "full_text": primary.get("full_text", ""),
            "details": primary,
        }

    try:
        secondary = _PDF_OCR.extract_text_from_pdf(str(document_path))
        return {
            "method": "ocr",
            "full_text": secondary.get("full_text", ""),
            "details": secondary,
        }
    except Exception as exc:
        return {
            "method": "unavailable",
            "full_text": "",
            "details": {"error": str(exc)},
        }


def maybe_generate_questions(source_text: str, job: Dict[str, Any], db: Database) -> Optional[List[Dict[str, Any]]]:
    if not job.get("generate_questions") or not source_text.strip():
        return None

    generator = QuestionGenerator()
    raw_questions = generator.generate_questions(source_text)

    sanitized_questions: List[Dict[str, Any]] = []
    for entry in raw_questions:
        question_text = entry.get("question", "").strip()
        if not question_text:
            continue
        sanitized_questions.append(
            {
                "question": question_text,
                "answer": None,
                "model_answer": entry.get("model_answer"),
                "improvement_tips": None,
                "score": None,
            }
        )

    speech_id = job.get("speech_id")
    if speech_id:
        db.store_questions(speech_id, sanitized_questions)

    generator.display_questions(raw_questions)
    return sanitized_questions or None


def process_job(job: Dict[str, Any], settings: Settings, s3_client: Any, db: Database) -> None:
    print(f"\n🚀 작업 시작: #{job['id']} ({job['video_source']})")
    video_path: Optional[Path] = None
    audio_path: Optional[Path] = None
    document_path: Optional[Path] = None
    cleanup_roots = [
        Path(settings.downloads_dir).resolve(),
        Path(settings.audio_output_dir).resolve(),
    ]
    try:
        speech_record: Optional[Dict[str, Any]] = None
        speech_uuid: Optional[UUID] = None
        speech_id_value = job.get("speech_id")
        if speech_id_value:
            try:
                speech_uuid = UUID(str(speech_id_value))
                speech_record = db.get_speech(speech_uuid)
            except ValueError:
                print(f"⚠️  잘못된 speech_id 형식입니다: {speech_id_value}")

        video_path = resolve_video_source(job, settings, s3_client)
        audio_path = extract_audio_from_video(video_path, Path(settings.audio_output_dir))
        print(f"🎧 오디오 추출 완료: {audio_path}")

        result = transcribe_audio(
            audio_path,
            model_size=job.get("model_size", "medium"),
            language=job.get("language"),
        )

        print("\n" + "=" * 50)
        print("📝 변환된 텍스트")
        print("=" * 50)
        print(result.get("text", ""))

        quality_info = analyze_transcription_quality(result)
        transcript_text = result.get("text", "")

        document_text = ""
        document_info: Optional[Dict[str, Any]] = None
        if speech_record:
            try:
                document_path = resolve_document_source(speech_record, settings, s3_client)
            except Exception as doc_exc:  # pylint: disable=broad-except
                print(f"⚠️  문서 처리 중 오류가 발생했습니다: {doc_exc}")
                document_info = {"error": str(doc_exc)}
            else:
                if document_path:
                    doc_result = extract_document_text(document_path)
                    document_text = doc_result.get("full_text", "") or ""
                    document_info = {
                        "method": doc_result.get("method"),
                        "characters": len(document_text),
                        "words": len(document_text.split()),
                        "path": str(document_path),
                        "full_text": document_text,
                        "details": doc_result.get("details"),
                    }

        combined_text_parts = [text for text in [transcript_text, document_text] if text and text.strip()]
        combined_source_text = "\n\n".join(combined_text_parts)

        if speech_uuid:
            db.update_speech_after_transcription(speech_uuid, transcript_text, document_text)

        questions = maybe_generate_questions(combined_source_text, job, db)

        metadata = {
            **quality_info,
            "language": result.get("language"),
            "model_size": job.get("model_size", "medium"),
            "speech_id": str(speech_uuid) if speech_uuid else None,
            "document": document_info,
        }
        db.mark_completed(job["id"], combined_source_text or transcript_text, metadata, questions)
        print(f"✅ 작업 완료: #{job['id']}")
    except Exception as exc:
        error_message = f"{exc.__class__.__name__}: {exc}"
        db.mark_failed(job["id"], error_message)
        print(f"❌ 작업 실패: #{job['id']} - {error_message}")
        traceback.print_exc()
    finally:
        _cleanup_temp_artifacts(cleanup_roots, video_path, audio_path, document_path)


def create_s3_client(settings: Settings) -> Any:
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key,
        aws_secret_access_key=settings.aws_secret_key,
    )


def main() -> None:
    settings = Settings.from_env()
    ensure_directory(Path(settings.audio_output_dir))
    ensure_directory(Path(settings.downloads_dir))

    db = Database(settings)
    db.init_schema()

    s3_client = create_s3_client(settings)

    processed_jobs = 0
    while True:
        job = db.fetch_next_job()
        if not job:
            if processed_jobs == 0:
                print("⏱️  대기 중인 작업이 없습니다.")
            break

        process_job(job, settings, s3_client, db)
        processed_jobs += 1

    print(f"\n총 {processed_jobs}개의 작업을 처리했습니다.")


if __name__ == "__main__":
    main()
