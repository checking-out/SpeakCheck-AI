import google.generativeai as genai
import os
from typing import List, Dict
import json

class QuestionGenerator:
    def __init__(self, api_key: str = None):
        """질문 생성기 초기화"""
        if api_key:
            genai.configure(api_key=api_key)
        else:
            # 환경변수에서 API 키 가져오기
            api_key = os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
        
        if not api_key:
            print("⚠️  Gemini API 키가 설정되지 않았습니다.")
            print("   환경변수 GEMINI_API_KEY를 설정하거나 API 키를 직접 입력해주세요.")
            print("   무료 API 키는 https://makersuite.google.com/app/apikey 에서 발급받을 수 있습니다.")
    
    def generate_questions(self, text: str, num_questions: int = 5, difficulty: str = "medium") -> List[Dict]:
        """
        텍스트를 바탕으로 질문들을 생성합니다.
        
        Args:
            text: 변환된 텍스트
            num_questions: 생성할 질문 수
            difficulty: 난이도 (easy, medium, hard)
        
        Returns:
            질문 리스트 (각 질문은 텍스트, 답변, 힌트 포함)
        """
        
        try:
            # Gemini 모델 초기화
            model = genai.GenerativeModel('gemini-1.5-pro')
            
            # 프롬프트 생성
            prompt = self._create_prompt(text, num_questions, difficulty)
            
            # Gemini API 호출
            response = model.generate_content(prompt)
            
            # 응답 파싱
            questions_text = response.text
            print(f"🔍 Gemini 응답 (디버그):\n{questions_text}\n")
            return self._parse_questions(questions_text)
            
        except Exception as e:
            print(f"❌ Gemini API 호출 중 오류 발생: {e}")
            print("   대체 질문 생성 방법을 사용합니다.")
            return self._generate_fallback_questions(text, num_questions)
    
    def _create_prompt(self, text: str, num_questions: int, difficulty: str) -> str:
        """질문 생성을 위한 프롬프트 생성"""
        
        difficulty_guide = {
            "easy": "기본적인 이해를 확인하는 쉬운 질문",
            "medium": "적당한 수준의 분석과 이해를 요구하는 질문", 
            "hard": "심화된 사고와 응용을 요구하는 어려운 질문"
        }
        
        return f"""
다음 텍스트를 바탕으로 {num_questions}개의 {difficulty_guide[difficulty]}을 생성해주세요.

텍스트:
{text}

각 질문에 대해 다음 형식으로 답변해주세요:
1. 질문: [질문 내용]
   답변: [정답]
   힌트: [힌트]
   유형: [객관식/주관식/서술형]

2. 질문: [질문 내용]
   답변: [정답]
   힌트: [힌트]
   유형: [객관식/주관식/서술형]

... (총 {num_questions}개)

질문은 텍스트의 핵심 내용을 다루되, 단순 암기가 아닌 이해와 사고를 요구하는 질문으로 만들어주세요.
"""
    
    def _parse_questions(self, questions_text: str) -> List[Dict]:
        """생성된 질문 텍스트를 파싱하여 구조화된 데이터로 변환"""
        questions = []
        
        # 정규표현식을 사용한 더 강력한 파싱
        import re
        
        # 질문 블록을 분리 (숫자. 질문: 패턴으로 시작)
        question_blocks = re.split(r'\n(?=\d+\.\s*질문:)', questions_text.strip())
        
        for block in question_blocks:
            if not block.strip():
                continue
                
            question = {}
            lines = block.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.')) and '질문:' in line:
                    # 질문 텍스트 추출
                    question["question"] = line.split('질문:', 1)[1].strip()
                elif line.startswith('답변:'):
                    question["answer"] = line.split('답변:', 1)[1].strip()
                elif line.startswith('힌트:'):
                    question["hint"] = line.split('힌트:', 1)[1].strip()
                elif line.startswith('유형:'):
                    question["type"] = line.split('유형:', 1)[1].strip()
            
            # 기본값 설정
            if "question" not in question:
                question["question"] = ""
            if "answer" not in question:
                question["answer"] = ""
            if "hint" not in question:
                question["hint"] = ""
            if "type" not in question:
                question["type"] = "주관식"
            
            if question["question"]:
                questions.append(question)
        
        return questions
    
    def _generate_fallback_questions(self, text: str, num_questions: int) -> List[Dict]:
        """OpenAI API를 사용할 수 없을 때의 대체 질문 생성"""
        print("🔄 기본 질문 생성 방법을 사용합니다...")
        
        # 텍스트를 문장으로 분할
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        
        questions = []
        for i in range(min(num_questions, len(sentences))):
            sentence = sentences[i]
            if len(sentence) < 10:  # 너무 짧은 문장은 건너뛰기
                continue
                
            # 간단한 질문 생성
            question = f"다음 문장의 핵심 내용은 무엇인가요? '{sentence[:50]}...'"
            answer = sentence
            hint = "문장을 다시 읽어보고 주요 키워드를 찾아보세요."
            
            questions.append({
                "question": question,
                "answer": answer,
                "hint": hint,
                "type": "주관식"
            })
        
        return questions
    
    def save_questions(self, questions: List[Dict], filename: str = "generated_questions.json"):
        """생성된 질문들을 JSON 파일로 저장"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(questions, f, ensure_ascii=False, indent=2)
            print(f"💾 질문이 {filename}에 저장되었습니다.")
        except Exception as e:
            print(f"❌ 파일 저장 중 오류 발생: {e}")
    
    def display_questions(self, questions: List[Dict]):
        """생성된 질문들을 보기 좋게 출력"""
        print("\n" + "="*60)
        print("📝 생성된 질문들")
        print("="*60)
        
        for i, q in enumerate(questions, 1):
            print(f"\n🔸 질문 {i} ({q.get('type', '주관식')})")
            print(f"   Q: {q['question']}")
            print(f"   A: {q['answer']}")
            print(f"   💡 힌트: {q['hint']}")
            print("-" * 50)

def main():
    """메인 실행 함수"""
    print("🤖 AI 질문 생성기")
    print("="*40)
    
    # 텍스트 입력
    print("변환된 텍스트를 입력하세요 (여러 줄 입력 후 빈 줄로 종료):")
    lines = []
    while True:
        line = input()
        if line.strip() == "":
            break
        lines.append(line)
    
    text = "\n".join(lines)
    
    if not text.strip():
        print("❌ 텍스트가 입력되지 않았습니다.")
        return
    
    # 설정 입력
    try:
        num_questions = int(input("\n생성할 질문 수 (기본값: 5): ") or "5")
        difficulty = input("난이도 (easy/medium/hard, 기본값: medium): ").strip() or "medium"
    except ValueError:
        num_questions = 5
        difficulty = "medium"
    
    # API 키 입력 (선택사항)
    api_key = input("\nGemini API 키 (선택사항, Enter로 건너뛰기): ").strip()
    if not api_key:
        api_key = None
    
    # 질문 생성기 초기화
    generator = QuestionGenerator(api_key)
    
    # 질문 생성
    print(f"\n🔄 {num_questions}개의 {difficulty} 난이도 질문을 생성 중...")
    questions = generator.generate_questions(text, num_questions, difficulty)
    
    # 결과 출력
    generator.display_questions(questions)
    
    # 저장 여부 확인
    save = input("\n💾 질문을 파일로 저장하시겠습니까? (y/n): ").lower().strip()
    if save == 'y':
        filename = input("파일명 (기본값: generated_questions.json): ").strip() or "generated_questions.json"
        generator.save_questions(questions, filename)

if __name__ == "__main__":
    main()
