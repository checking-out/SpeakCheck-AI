import json
import os
from pdf_to_text import PDFTextExtractor
from question_generator import QuestionGenerator

class PDFQuestionGenerator:
    def __init__(self, gemini_api_key: str = None):
        """PDF 텍스트 추출 + AI 질문 생성 통합 클래스"""
        self.pdf_extractor = PDFTextExtractor()
        self.question_generator = QuestionGenerator(gemini_api_key)
    
    def generate_questions_from_pdf(self, pdf_path: str, num_questions: int = 5, difficulty: str = "medium") -> dict:
        """PDF에서 텍스트를 추출하고 AI 질문을 생성합니다."""
        
        print("🔍 PDF에서 텍스트 추출 중...")
        print("="*50)
        
        # 1. PDF에서 텍스트 추출
        pdf_result = self.pdf_extractor.extract_text(pdf_path)
        
        if not pdf_result['success']:
            return {
                'success': False,
                'error': f"PDF 텍스트 추출 실패: {pdf_result['error']}",
                'pdf_result': pdf_result
            }
        
        print(f"\n✅ PDF 텍스트 추출 완료!")
        print(f"   📄 페이지: {pdf_result['total_pages']}")
        print(f"   📝 총 문자: {pdf_result['total_characters']}")
        print(f"   📝 총 단어: {pdf_result['total_words']}")
        
        # 2. AI 질문 생성
        print(f"\n🤖 AI 질문 생성 중... ({num_questions}개, {difficulty} 난이도)")
        print("="*50)
        
        questions = self.question_generator.generate_questions(
            pdf_result['full_text'], 
            num_questions, 
            difficulty
        )
        
        # 3. 결과 통합
        result = {
            'success': True,
            'pdf_info': {
                'file_name': pdf_result['file_name'],
                'total_pages': pdf_result['total_pages'],
                'total_characters': pdf_result['total_characters'],
                'total_words': pdf_result['total_words'],
                'method': pdf_result['method']
            },
            'questions': questions,
            'full_text': pdf_result['full_text'],
            'extraction_info': {
                'num_questions': num_questions,
                'difficulty': difficulty
            }
        }
        
        return result
    
    def display_results(self, result: dict):
        """결과를 콘솔에 출력합니다."""
        if not result['success']:
            print(f"❌ 오류: {result['error']}")
            return
        
        print("\n" + "="*60)
        print("📄 PDF → AI 질문 생성 결과")
        print("="*60)
        
        # PDF 정보
        pdf_info = result['pdf_info']
        print(f"📁 파일명: {pdf_info['file_name']}")
        print(f"📄 총 페이지: {pdf_info['total_pages']}")
        print(f"📝 총 문자: {pdf_info['total_characters']}")
        print(f"📝 총 단어: {pdf_info['total_words']}")
        print(f"🔧 추출 방법: {pdf_info['method']}")
        
        # 질문 정보
        extraction_info = result['extraction_info']
        print(f"🤖 생성된 질문 수: {extraction_info['num_questions']}")
        print(f"🎯 난이도: {extraction_info['difficulty']}")
        
        # 질문들 출력
        print("\n" + "-"*60)
        print("❓ 생성된 질문들")
        print("-"*60)
        
        for i, question in enumerate(result['questions'], 1):
            print(f"\n🔸 질문 {i}")
            print(f"   질문: {question.get('question', 'N/A')}")
            if 'answer' in question and question['answer']:
                print(f"   답변: {question['answer']}")
            if 'hint' in question and question['hint']:
                print(f"   힌트: {question['hint']}")
            if 'type' in question:
                print(f"   유형: {question['type']}")
    
    def save_results(self, result: dict, output_file: str = None):
        """결과를 JSON 파일로 저장합니다."""
        if not result['success']:
            print("❌ 저장할 결과가 없습니다.")
            return
        
        if not output_file:
            base_name = os.path.splitext(result['pdf_info']['file_name'])[0]
            output_file = f"{base_name}_questions.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"💾 결과가 {output_file}에 저장되었습니다.")
        except Exception as e:
            print(f"❌ 파일 저장 중 오류 발생: {e}")

def main():
    """메인 실행 함수"""
    print("🔍 PDF → AI 질문 생성기")
    print("="*40)
    
    # PDF 파일 경로 입력
    pdf_path = input("PDF 파일 경로를 입력하세요: ").strip()
    
    if not pdf_path:
        print("❌ PDF 파일 경로가 입력되지 않았습니다.")
        return
    
    # 질문 생성 설정
    try:
        num_questions = int(input("생성할 질문 수 (기본값: 5): ").strip() or "5")
        difficulty = input("난이도 (easy/medium/hard, 기본값: medium): ").strip() or "medium"
    except ValueError:
        num_questions = 5
        difficulty = "medium"
    
    # Gemini API 키 확인
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("\n⚠️  Gemini API 키가 설정되지 않았습니다.")
        api_key = input("Gemini API 키를 입력하세요 (또는 Enter로 건너뛰기): ").strip()
        if not api_key:
            print("❌ API 키가 필요합니다.")
            return
    
    try:
        # PDF 질문 생성기 초기화
        pdf_qg = PDFQuestionGenerator(api_key)
        
        # PDF에서 질문 생성
        result = pdf_qg.generate_questions_from_pdf(pdf_path, num_questions, difficulty)
        
        # 결과 출력
        pdf_qg.display_results(result)
        
        # 저장 여부 확인
        if result['success']:
            save = input("\n💾 결과를 JSON 파일로 저장하시겠습니까? (y/n): ").lower().strip()
            if save == 'y':
                filename = input("파일명 (기본값: 자동생성): ").strip()
                if not filename:
                    filename = None
                pdf_qg.save_results(result, filename)
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()
