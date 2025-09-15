import os
import subprocess
import whisper

def extract_audio_from_video(video_path, output_dir="audio"):
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    output_path = os.path.join(output_dir, f"{base_name}.mp3")

    if not os.path.isfile(output_path):
        command = [
            "ffmpeg", "-i", video_path,
            "-vn",
            "-acodec", "mp3",
            "-ab", "192k",
            "-ar", "44100",
            output_path
        ]
        subprocess.run(command, check=True)
    return output_path

def transcribe_audio(audiofile, model_size="medium", language=None): # 맥 죽을거 같으면 medium대신 small ㄱㄱ large는 내꺼도 죽는다
    model = whisper.load_model(model_size)
    
    # 발음 이슈를 고려한 옵션들
    transcribe_options = {
        "language": language,
        "fp16": False,  # CPU에서는 FP32 사용
        "verbose": True,  # 상세한 로그 출력
        "word_timestamps": True,  # 단어별 타임스탬프
        "condition_on_previous_text": True,  # 이전 텍스트를 고려
        "compression_ratio_threshold": 2.4,  # 압축률 임계값 (너무 반복적인 텍스트 감지)
        "logprob_threshold": -1.0,  # 로그 확률 임계값 (낮은 확률의 단어 감지)
        "no_speech_threshold": 0.6,  # 무음 감지 임계값
    }
    
    result = model.transcribe(audiofile, **transcribe_options)
    return result

def analyze_transcription_quality(result):
    """변환 품질을 분석하고 개선 제안을 제공"""
    text = result["text"]
    segments = result.get("segments", [])
    
    print("\n" + "="*50)
    print("📊 변환 품질 분석")
    print("="*50)
    
    # 기본 통계
    word_count = len(text.split())
    char_count = len(text)
    segment_count = len(segments)
    
    print(f"📝 총 단어 수: {word_count}")
    print(f"📝 총 문자 수: {char_count}")
    print(f"📝 구간 수: {segment_count}")
    
    # 신뢰도 분석
    if segments:
        avg_prob = sum(seg.get("avg_logprob", 0) for seg in segments) / len(segments)
        print(f"📊 평균 신뢰도: {avg_prob:.2f}")
        
        # 낮은 신뢰도 구간 찾기
        low_confidence_segments = [seg for seg in segments if seg.get("avg_logprob", 0) < -1.0]
        if low_confidence_segments:
            print(f"⚠️  낮은 신뢰도 구간: {len(low_confidence_segments)}개")
            print("   시간대별 낮은 신뢰도 구간:")
            for seg in low_confidence_segments[:3]:  # 처음 3개만 표시
                start_time = seg.get("start", 0)
                end_time = seg.get("end", 0)
                text_preview = seg.get("text", "")[:50] + "..." if len(seg.get("text", "")) > 50 else seg.get("text", "")
                print(f"   {start_time:.1f}s-{end_time:.1f}s: {text_preview}")
    
    # 개선 제안
    print("\n💡 개선 제안:")
    if avg_prob < -0.5:
        print("   • 발음이 불분명할 수 있습니다. 더 큰 모델을 사용해보세요 (large)")
        print("   • 배경 소음이 있을 수 있습니다. 조용한 환경에서 녹음해보세요")
    if word_count < 10:
        print("   • 텍스트가 너무 짧습니다. 더 긴 오디오를 사용해보세요")
    if segment_count > 50:
        print("   • 구간이 너무 많습니다. 연속적인 발화를 시도해보세요")
    
    return {
        "word_count": word_count,
        "avg_confidence": avg_prob if segments else 0,
        "low_confidence_segments": len(low_confidence_segments) if segments else 0
    }

# 사용자로부터 비디오 파일 경로 입력받기
video_file = input("비디오 파일 경로를 입력하세요: ")

if not os.path.isfile(video_file):
    print(f"파일을 찾을 수 없습니다: {video_file}")
    exit(1)

# 언어 선택
print("\n언어를 선택하세요:")
print("1. 자동 감지 (권장)")
print("2. 한국어")
print("3. 영어")
print("4. 일본어")
print("5. 중국어")

lang_choice = input("선택 (1-5): ").strip()

language_map = {
    "1": None,      # 자동 감지
    "2": "ko",      # 한국어
    "3": "en",      # 영어
    "4": "ja",      # 일본어
    "5": "zh"       # 중국어
}

selected_language = language_map.get(lang_choice, None)
if selected_language is None and lang_choice != "1":
    print("잘못된 선택입니다. 자동 감지를 사용합니다.")
    selected_language = None

audio_path = extract_audio_from_video(video_file)
print("오디오 파일 경로:", audio_path)

if os.path.isfile(audio_path):
    print(f"\n음성을 텍스트로 변환 중... (언어: {'자동 감지' if selected_language is None else selected_language})")
    result = transcribe_audio(audio_path, language=selected_language)
    
    print("\n" + "="*50)
    print("📝 변환된 텍스트")
    print("="*50)
    print(result["text"])
    
    # 품질 분석
    quality_info = analyze_transcription_quality(result)
    
    # 질문 생성 옵션
    generate_questions = input("\n🤖 이 텍스트로 AI 질문을 생성하시겠습니까? (y/n): ").lower().strip()
    if generate_questions == 'y':
        print("\n" + "="*50)
        print("🤖 AI 질문 생성기 실행")
        print("="*50)
        
        # question_generator 모듈 import 및 실행
        try:
            from question_generator import QuestionGenerator
            
            # 질문 생성기 초기화
            generator = QuestionGenerator()
            
            # 질문 수와 난이도 설정
            try:
                num_questions = int(input("생성할 질문 수 (기본값: 5): ") or "5")
                difficulty = input("난이도 (easy/medium/hard, 기본값: medium): ").strip() or "medium"
            except ValueError:
                num_questions = 5
                difficulty = "medium"
            
            # 질문 생성
            print(f"\n🔄 {num_questions}개의 {difficulty} 난이도 질문을 생성 중...")
            questions = generator.generate_questions(result["text"], num_questions, difficulty)
            
            # 결과 출력
            generator.display_questions(questions)
            
            # 저장 여부 확인
            save = input("\n💾 질문을 파일로 저장하시겠습니까? (y/n): ").lower().strip()
            if save == 'y':
                filename = input("파일명 (기본값: generated_questions.json): ").strip() or "generated_questions.json"
                generator.save_questions(questions, filename)
                
        except ImportError:
            print("❌ question_generator.py 파일을 찾을 수 없습니다.")
        except Exception as e:
            print(f"❌ 질문 생성 중 오류 발생: {e}")
    
    # 추가 옵션 제안
    if quality_info["avg_confidence"] < -0.5:
        print("\n🔄 개선을 위한 추가 옵션:")
        print("   • 더 큰 모델 사용 (large) - 더 정확하지만 느림")
        print("   • 다른 언어 설정 시도")
        print("   • 오디오 품질 개선 후 재시도")
        
        retry = input("\n다른 모델로 다시 시도하시겠습니까? (y/n): ").lower().strip()
        if retry == 'y':
            print("\n더 큰 모델로 재시도 중...")
            result_large = transcribe_audio(audio_path, model_size="large", language=selected_language)
            print("\n" + "="*50)
            print("📝 개선된 변환 결과")
            print("="*50)
            print(result_large["text"])
            analyze_transcription_quality(result_large)
else:
    print("오디오 추출에 실패했습니다.")