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

def transcribe_audio(audiofile, model_size="medium"): # 맥 죽을거 같으면 medium대신 small ㄱㄱ large는 내꺼도 죽는다
    model = whisper.load_model(model_size)
    result = model.transcribe(audiofile, language="ko")
    return result["text"]

video_file = "p_20250910_조아라한국사(99).mp4"
audio_path = extract_audio_from_video(video_file)
print("오디오 파일 경로:", audio_path)

if os.path.isfile(audio_path):
    transcription = transcribe_audio(audio_path)
    print("변환된 텍스트:")
    print(transcription)
else:
    print("오디오 추출에 실패했습니다.")
