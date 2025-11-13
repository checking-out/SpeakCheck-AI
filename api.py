from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import UUID

import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ai_feedback import AIFeedback
from config import Settings
from database import Database
from question_generator import QuestionGenerator


class SpeechCreateRequest(BaseModel):
    stage_id: UUID = Field(..., description="연결될 Stage ID")
    title: Optional[str] = Field(None, max_length=255, description="발표 제목")


class SpeechVideoUpdateRequest(BaseModel):
    video_source: str = Field(..., description="수정할 영상의 로컬 경로 또는 S3 키/URL")


class SpeechDocumentUpdateRequest(BaseModel):
    document_url: str = Field(..., description="수정할 문서(PPT) 파일 경로 또는 S3 키/URL")


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    video_source: str
    speech_id: Optional[UUID]
    stage_id: Optional[UUID]
    user_id: Optional[UUID]
    language: Optional[str]
    model_size: Optional[str]
    generate_questions: Optional[bool]
    status: str
    transcript: Optional[str]
    transcript_metadata: Optional[Dict[str, Any]]
    questions: Optional[Any]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime


class SpeechRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    stage_id: UUID
    title: str
    speech_name: Optional[str]
    video_source: Optional[str]
    document_url: Optional[str]
    created_at: datetime
    updated_at: datetime


class SpeechVideoResponse(BaseModel):
    speech: SpeechRecord
    job: JobResponse


class StageWithSpeeches(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    stage_name: str
    situation: Optional[str]
    check_list_url: Optional[str]
    created_at: datetime
    updated_at: datetime
    speeches: List[SpeechRecord]


class QuestionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    speech_id: UUID
    question: str
    answer: Optional[str]
    model_answer: Optional[str]
    improvement_tips: Optional[str]
    user_answer: Optional[str]
    ai_feedback: Optional[str]
    score: Optional[int]
    created_at: datetime
    updated_at: datetime


class QuestionAnswerRequest(BaseModel):
    answer: str = Field(..., description="사용자의 답변")
    request_feedback: bool = Field(True, description="AI 피드백 생성 여부")


class QuestionAnswerResponse(BaseModel):
    question: QuestionRecord
    feedback: Optional[str]
    score: Optional[int]


class SpeechFeedbackResponse(BaseModel):
    speech_id: UUID
    feedback: str
    scores: Dict[str, Optional[int]]


settings = Settings.from_env()
database = Database(settings)
database.init_schema()
feedback_service = AIFeedback()
question_generator = QuestionGenerator()

app = FastAPI(title="SpeakCheck Whisper API", version="1.0.0")

# ✅ 미들웨어 먼저
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ 그 다음 OPTIONS 핸들러
@app.options("/{rest_of_path:path}", include_in_schema=False)
def handle_options(rest_of_path: str) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _serialize_job(raw: Dict[str, Any]) -> JobResponse:
    return JobResponse.model_validate(raw)


def _serialize_speech(raw: Dict[str, Any]) -> SpeechRecord:
    return SpeechRecord.model_validate(raw)


def _serialize_question(raw: Dict[str, Any]) -> QuestionRecord:
    return QuestionRecord.model_validate(raw)


def _serialize_stage(stage: Dict[str, Any], speeches: List[Dict[str, Any]]) -> StageWithSpeeches:
    return StageWithSpeeches.model_validate(
        {
            **stage,
            "speeches": [SpeechRecord.model_validate(speech) for speech in speeches],
        }
    )


def get_current_user_id(authorization: Optional[str] = Header(None)) -> UUID:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization scheme",
        )

    token = authorization.split(" ", maxsplit=1)[1].strip()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:  # type: ignore[attr-defined]
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    user_id = payload.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    try:
        return UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload") from exc


def _derive_title(source: str, provided: Optional[str]) -> str:
    if provided:
        return provided

    parsed = urlparse(source)
    candidate: Optional[str] = None

    if parsed.path:
        candidate = Path(parsed.path).stem

    if not candidate:
        candidate = Path(source).stem if "://" not in source else None

    if candidate:
        candidate = candidate.strip()

    return candidate or "Untitled Speech"


def _ensure_stage_ownership(stage_id: UUID, current_user_id: UUID) -> Dict[str, Any]:
    stage = database.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    stage_owner = stage.get("user_id")
    if stage_owner and UUID(str(stage_owner)) != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Stage does not belong to user")

    return stage


def _extract_document_text_from_metadata(metadata: Any) -> str:
    if not isinstance(metadata, dict):
        return ""
    document_info = metadata.get("document")
    if not isinstance(document_info, dict):
        return ""

    for key in ("full_text",):
        value = document_info.get(key)
        if isinstance(value, str) and value.strip():
            return value

    details = document_info.get("details")
    if isinstance(details, dict):
        value = details.get("full_text")
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _sanitize_generated_questions(raw_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sanitized: List[Dict[str, Any]] = []
    for entry in raw_questions:
        question_text = str(entry.get("question", "")).strip()
        if not question_text:
            continue
        sanitized.append(
            {
                "question": question_text,
                "answer": None,
                "model_answer": (entry.get("model_answer") or "").strip() or None,
                "improvement_tips": None,
                "score": entry.get("score"),
            }
        )
    return sanitized


@app.get("/healthz", tags=["health"])
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.options("/{rest_of_path:path}", include_in_schema=False)
def handle_options(rest_of_path: str) -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/speech",
    response_model=SpeechRecord,
    status_code=status.HTTP_201_CREATED,
    tags=["speech"],
)
def create_speech(
    request: SpeechCreateRequest,
    current_user_id: UUID = Depends(get_current_user_id),
) -> SpeechRecord:
    _ensure_stage_ownership(request.stage_id, current_user_id)

    title = request.title.strip() if request.title else "Untitled Speech"

    speech = database.create_speech(
        stage_id=request.stage_id,
        title=title or "Untitled Speech",
    )
    return _serialize_speech(speech)


@app.get("/speech/{speech_id}", response_model=SpeechRecord, tags=["speech"])
def get_speech(speech_id: UUID, current_user_id: UUID = Depends(get_current_user_id)) -> SpeechRecord:
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    _ensure_stage_ownership(UUID(str(speech["stage_id"])), current_user_id)
    return _serialize_speech(speech)


@app.get("/question/{speech_id}", response_model=List[QuestionRecord], tags=["question"])
def get_questions_for_speech(speech_id: UUID, current_user_id: UUID = Depends(get_current_user_id)) -> List[QuestionRecord]:
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    _ensure_stage_ownership(UUID(str(speech["stage_id"])), current_user_id)
    questions = database.list_questions_for_speech(speech_id)
    if questions:
        return [_serialize_question(q) for q in questions]

    job = database.get_latest_completed_job_for_speech(speech_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No questions available")

    generated_questions = job.get("questions")
    if isinstance(generated_questions, list) and generated_questions:
        speech_questions = database.upsert_questions(speech_id, generated_questions)
        return [_serialize_question(q) for q in speech_questions]

    transcript_text = job.get("transcript") or ""
    document_text = _extract_document_text_from_metadata(job.get("transcript_metadata"))

    combined_parts = [part for part in [transcript_text, document_text] if isinstance(part, str) and part.strip()]
    if not combined_parts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No questions available")

    combined_text = "\n\n".join(combined_parts)
    try:
        raw_questions = question_generator.generate_questions(combined_text)
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Failed to generate questions: {exc}") from exc

    sanitized_questions = _sanitize_generated_questions(raw_questions)
    if not sanitized_questions:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No questions available")

    speech_questions = database.upsert_questions(speech_id, sanitized_questions)
    return [_serialize_question(q) for q in speech_questions]


@app.post(
    "/question/answer/{question_id}",
    response_model=QuestionAnswerResponse,
    tags=["question"],
)
def submit_question_answer(
    question_id: UUID,
    request: QuestionAnswerRequest,
    current_user_id: UUID = Depends(get_current_user_id),
) -> QuestionAnswerResponse:
    question = database.get_question(question_id)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    speech_id = UUID(str(question["speech_id"]))
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    _ensure_stage_ownership(UUID(str(speech["stage_id"])), current_user_id)

    feedback_text: Optional[str] = None
    feedback_score: Optional[int] = None

    if request.request_feedback:
        job = database.get_latest_completed_job_for_speech(speech_id)
        transcript = job.get("transcript") if job else ""
        context_parts = [transcript or ""]
        metadata = job.get("transcript_metadata") if job else None
        if isinstance(metadata, dict):
            document_info = metadata.get("document")
            if isinstance(document_info, dict):
                doc_details = document_info.get("details")
                if isinstance(doc_details, dict):
                    doc_text = doc_details.get("full_text")
                    if doc_text:
                        context_parts.append(str(doc_text))
        context_text = "\n\n".join(part for part in context_parts if part)

        feedback_payload = feedback_service.generate_answer_feedback(
            question=question.get("question"),
            ideal_answer=question.get("model_answer"),
            user_answer=request.answer,
            context=context_text,
        )
        feedback_text = feedback_payload.get("feedback")
        feedback_score = feedback_payload.get("score")

    database.update_question_feedback(
        question_id,
        user_answer=request.answer,
        ai_feedback=feedback_text or "",
        score=feedback_score,
    )

    updated_question = database.get_question(question_id)
    if not updated_question:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update question")

    return QuestionAnswerResponse(
        question=_serialize_question(updated_question),
        feedback=feedback_text,
        score=feedback_score,
    )


@app.post(
    "/speech/{speech_id}/feedback",
    response_model=SpeechFeedbackResponse,
    tags=["speech"],
)
def generate_speech_feedback(
    speech_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
) -> SpeechFeedbackResponse:
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    stage_id = UUID(str(speech["stage_id"]))
    _ensure_stage_ownership(stage_id, current_user_id)

    job = database.get_latest_completed_job_for_speech(speech_id)
    if not job or not job.get("transcript"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Completed transcription not found")

    transcript = job.get("transcript", "")
    document_text = None
    metadata = job.get("transcript_metadata")
    if isinstance(metadata, dict):
        document_info = metadata.get("document")
        if isinstance(document_info, dict):
            doc_details = document_info.get("details")
            if isinstance(doc_details, dict):
                document_text = doc_details.get("full_text")

    feedback_payload = feedback_service.generate_speech_feedback(
        transcript=transcript,
        document_text=document_text,
        video_source=speech.get("video_source"),
    )

    return SpeechFeedbackResponse(
        speech_id=speech_id,
        feedback=feedback_payload.get("feedback", ""),
        scores=feedback_payload.get("scores", {}),
    )


@app.delete("/speech/{speech_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["speech"])
def delete_speech(speech_id: UUID, current_user_id: UUID = Depends(get_current_user_id)) -> None:
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    _ensure_stage_ownership(UUID(str(speech["stage_id"])), current_user_id)
    database.delete_speech(speech_id)


@app.get("/stage/{stage_id}", response_model=StageWithSpeeches, tags=["stage"])
def get_stage_with_speeches(stage_id: UUID, current_user_id: UUID = Depends(get_current_user_id)) -> StageWithSpeeches:
    stage = database.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")

    _ensure_stage_ownership(stage_id, current_user_id)
    speeches = database.list_speeches_for_stage(stage_id)
    return _serialize_stage(stage, speeches)


@app.put(
    "/speech/video/{speech_id}",
    response_model=SpeechVideoResponse,
    tags=["speech"],
)
def update_speech_video(
    speech_id: UUID,
    request: SpeechVideoUpdateRequest,
    current_user_id: UUID = Depends(get_current_user_id),
) -> SpeechVideoResponse:
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    stage_id = UUID(str(speech["stage_id"]))
    _ensure_stage_ownership(stage_id, current_user_id)

    speech_title = _derive_title(request.video_source, None)
    updated_speech = database.update_speech_video(
        speech_id=speech_id,
        title=speech_title,
        video_source=request.video_source,
    )

    job = database.create_job(
        video_source=request.video_source,
        user_id=current_user_id,
        stage_id=stage_id,
        speech_id=speech_id,
    )

    return SpeechVideoResponse(
        speech=_serialize_speech(updated_speech),
        job=_serialize_job(job),
    )


@app.put(
    "/speech/document/{speech_id}",
    response_model=SpeechRecord,
    tags=["speech"],
)
def update_speech_document(
    speech_id: UUID,
    request: SpeechDocumentUpdateRequest,
    current_user_id: UUID = Depends(get_current_user_id),
) -> SpeechRecord:
    speech = database.get_speech(speech_id)
    if not speech:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Speech not found")

    stage_id = UUID(str(speech["stage_id"]))
    _ensure_stage_ownership(stage_id, current_user_id)

    speech_title = _derive_title(request.document_url, None)
    updated_speech = database.update_speech_document(
        speech_id=speech_id,
        title=speech_title,
        document_url=request.document_url,
    )

    return _serialize_speech(updated_speech)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8081, reload=True)
