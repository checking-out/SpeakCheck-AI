import os
from typing import Dict, Optional

import google.generativeai as genai


class AIFeedback:
    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("GEMINI_API_KEY")
        if key:
            genai.configure(api_key=key)
        else:
            print("⚠️  Gemini API 키가 설정되지 않았습니다. ai_feedback.py 기능이 제한됩니다.")

    def generate_answer_feedback(
        self,
        *,
        question: str,
        ideal_answer: Optional[str],
        user_answer: str,
        context: str,
    ) -> Dict[str, Optional[str]]:
        prompt = f"""
당신은 스피치 코치입니다. 아래 정보를 참고하여 학습자 답변을 평가하고 피드백을 작성하세요.

[질문]
{question}

[이상적인 답변 요약]
{ideal_answer or '제공되지 않음'}

[맥락 텍스트]
{context[:4000]}

[학습자 답변]
{user_answer}

아래 형식을 따라 간결하게 한국어로 답변하세요.

점수(0~100): ...
강점: ...
보완할점: ...
핵심키워드: ...
"""
        try:
            model = genai.GenerativeModel("gemini-1.0-pro")
            response = model.generate_content(prompt)
            text = response.text.strip()
            score = self._extract_score(text)
            return {
                "feedback": text,
                "score": score,
            }
        except Exception:
            return self._fallback_answer_feedback(ideal_answer, user_answer)

    def generate_speech_feedback(
        self,
        *,
        transcript: str,
        document_text: Optional[str],
        video_source: Optional[str],
    ) -> Dict[str, Optional[str]]:
        prompt = f"""
당신은 발표 코치입니다. 아래 발표 스크립트와 참고 자료(없으면 '없음'이라 명시)를 참고하여 발표 피드백을 작성하세요.

[발표 스크립트]
{transcript[:6000] or '없음'}

[발표 자료]
{(document_text or '없음')[:4000]}

가능하다면 영상 출처도 참고하세요: {video_source or '미제공'}

다음 형식의 JSON만 출력하세요 (여분 텍스트 금지):
{{
  "feedback": "5~7줄로 요약된 한국어 피드백",
  "scores": {{
    "시선처리": 0에서 100 사이 정수,
    "제스처": 0에서 100 사이 정수,
    "말의 속도": 0에서 100 사이 정수,
    "억양": 0에서 100 사이 정수,
    "시각자료구성": 0에서 100 사이 정수,
    "내용구성": 0에서 100 사이 정수
  }}
}}
"""
        try:
            model = genai.GenerativeModel("gemini-1.0-pro")
            response = model.generate_content(prompt)
            text = response.text.strip()
            import json

            data = json.loads(text)
            feedback = str(data.get("feedback", "")).strip()
            scores = data.get("scores") or {}
            normalized_scores = {
                key: int(scores.get(key, 0)) if isinstance(scores.get(key), (int, float)) else None
                for key in ["시선처리", "제스처", "말의 속도", "억양", "시각자료구성", "내용구성"]
            }
            return {
                "feedback": feedback,
                "scores": normalized_scores,
            }
        except Exception:
            return self._fallback_speech_feedback(transcript, document_text)

    @staticmethod
    def _extract_score(text: str) -> Optional[int]:
        for line in text.splitlines():
            if "점수" in line:
                digits = "".join(ch for ch in line if ch.isdigit())
                if digits:
                    try:
                        return max(0, min(100, int(digits)))
                    except ValueError:
                        return None
        return None

    @staticmethod
    def _fallback_answer_feedback(
        ideal_answer: Optional[str],
        user_answer: str,
    ) -> Dict[str, Optional[str]]:
        ideal_tokens = set()
        if ideal_answer:
            ideal_tokens = {
                token for token in ideal_answer.lower().split() if len(token) > 1
            }
        user_tokens = {
            token for token in user_answer.lower().split() if len(token) > 1
        }
        overlap = ideal_tokens & user_tokens
        score = 0
        if ideal_tokens:
            score = int((len(overlap) / len(ideal_tokens)) * 100)
        elif user_tokens:
            score = min(100, len(user_tokens) * 10)

        strengths = []
        areas = []
        if score >= 70:
            strengths.append("핵심 키워드를 잘 언급했습니다.")
        elif score >= 30:
            strengths.append("답변의 방향은 파악했습니다.")
            areas.append("핵심 용어를 더 명확히 설명해 주세요.")
        else:
            areas.append("질문의 의도를 다시 확인하고 주요 개념을 언급해 주세요.")

        if not user_answer.strip():
            areas.append("답변을 입력하면 피드백을 받을 수 있습니다.")

        feedback_lines = [
            f"점수(예상): {score}",
            f"강점: {', '.join(strengths) if strengths else '강점을 파악하기 어렵습니다.'}",
            f"보완할점: {', '.join(areas) if areas else '현재 답변을 계속 유지해 보세요.'}",
        ]
        return {
            "feedback": "\n".join(feedback_lines),
            "score": score,
        }

    @staticmethod
    def _fallback_speech_feedback(
        transcript: str,
        document_text: Optional[str],
    ) -> Dict[str, Optional[str]]:
        transcript_length = len(transcript.split())
        doc_length = len((document_text or "").split())

        base_feedback = [
            "• 전반적으로 발표 흐름이 자연스럽게 이어지도록 구성해 보세요." if transcript_length < 200 else
            "• 발표 스크립트가 충분히 길어 핵심 내용을 잘 담고 있습니다.",
            "• 시각 자료는 핵심 메시지가 잘 드러나도록 간결하게 정리해 보세요." if doc_length < 100 else
            "• 시각 자료 분량이 충분하니 슬라이드마다 전달하고 싶은 메시지를 강조해 주세요.",
            "• 중요한 메시지를 전달할 때는 목소리의 억양과 속도를 조절해 청중의 집중을 이끌어 보세요."
        ]

        scores = {
            "시선처리": 60,
            "제스처": 60,
            "말의 속도": 60 if transcript_length < 200 else 75,
            "억양": 60,
            "시각자료구성": 55 if doc_length < 80 else 70,
            "내용구성": 65 if transcript_length < 200 else 80,
        }

        return {
            "feedback": "\n".join(base_feedback),
            "scores": scores,
        }
