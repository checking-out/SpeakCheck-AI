import pdfplumber
import os
import json
from typing import Dict, List, Optional

class PDFTextExtractor:
    def __init__(self):
        """PDF 직접 텍스트 추출기 초기화 (pdfplumber 전용)"""
        pass
    
    def extract_with_pdfplumber(self, pdf_path: str) -> Dict:
        """pdfplumber를 사용한 텍스트 추출"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                results = {
                    'method': 'pdfplumber',
                    'total_pages': len(pdf.pages),
                    'pages': [],
                    'full_text': '',
                    'success': True,
                    'error': None
                }
                
                for i, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text()
                        cleaned_text = self._clean_text(text) if text else ""
                        
                        page_info = {
                            'page_number': i + 1,
                            'raw_text': text or "",
                            'cleaned_text': cleaned_text,
                            'character_count': len(cleaned_text),
                            'word_count': len(cleaned_text.split()) if cleaned_text else 0
                        }
                        
                        results['pages'].append(page_info)
                        results['full_text'] += cleaned_text + '\n\n'
                        
                    except Exception as e:
                        results['pages'].append({
                            'page_number': i + 1,
                            'raw_text': '',
                            'cleaned_text': f"❌ 페이지 {i+1} 추출 실패: {e}",
                            'character_count': 0,
                            'word_count': 0
                        })
                
                return results
                
        except Exception as e:
            return {
                'method': 'pdfplumber',
                'total_pages': 0,
                'pages': [],
                'full_text': '',
                'success': False,
                'error': str(e)
            }
    
    def extract_text(self, pdf_path: str) -> Dict:
        """PDF에서 텍스트 추출 (pdfplumber 사용)"""
        if not os.path.exists(pdf_path):
            return {
                'success': False,
                'error': f"PDF 파일을 찾을 수 없습니다: {pdf_path}"
            }
        
        print(f"📄 PDF 파일 분석 중: {os.path.basename(pdf_path)}")
        print("="*50)
        
        # pdfplumber로 텍스트 추출
        result = self.extract_with_pdfplumber(pdf_path)
        
        if not result['success']:
            print(f"❌ 텍스트 추출 실패: {result['error']}")
            return result
        
        print(f"✅ 텍스트 추출 성공!")
        print(f"   📄 페이지: {result['total_pages']}")
        print(f"   📝 총 문자: {len(result['full_text'])}")
        print(f"   📝 총 단어: {len(result['full_text'].split())}")
        
        return {
            'success': True,
            'file_name': os.path.basename(pdf_path),
            'method': 'pdfplumber',
            'total_pages': result['total_pages'],
            'total_characters': len(result['full_text']),
            'total_words': len(result['full_text'].split()),
            'full_text': result['full_text'],
            'pages': result['pages']
        }
    
    def _clean_text(self, text: str) -> str:
        """텍스트 정리"""
        if not text:
            return ""
        
        # 불필요한 공백 제거
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if line:  # 빈 줄이 아닌 경우만 추가
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def display_results(self, results: Dict):
        """결과 출력"""
        if not results['success']:
            print(f"❌ 오류: {results['error']}")
            return
        
        print("\n" + "="*60)
        print("📄 PDF 직접 텍스트 추출 결과")
        print("="*60)
        
        print(f"📁 파일명: {results['file_name']}")
        print(f"🔧 사용된 방법: {results['method']}")
        print(f"📄 총 페이지: {results['total_pages']}")
        print(f"📝 총 문자: {results['total_characters']}")
        print(f"📝 총 단어: {results['total_words']}")
        
        print("\n" + "-"*60)
        print("📄 페이지별 내용")
        print("-"*60)
        
        for page in results['pages']:
            print(f"\n🔸 페이지 {page['page_number']}")
            print(f"   단어: {page['word_count']}, 문자: {page['character_count']}")
            print("   내용:")
            if page['cleaned_text']:
                # 긴 텍스트는 일부만 표시
                preview = page['cleaned_text'][:200] + "..." if len(page['cleaned_text']) > 200 else page['cleaned_text']
                print(f"   {preview}")
            else:
                print("   (텍스트 없음)")
        
        print("\n" + "="*60)
        print("📝 전체 텍스트")
        print("="*60)
        print(results['full_text'])
    
    def save_results(self, results: Dict, output_file: str = None):
        """결과를 JSON 파일로 저장"""
        if not results['success']:
            print("❌ 저장할 결과가 없습니다.")
            return
        
        if not output_file:
            base_name = os.path.splitext(results['file_name'])[0]
            output_file = f"{base_name}_direct_extract.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"💾 결과가 {output_file}에 저장되었습니다.")
        except Exception as e:
            print(f"❌ 파일 저장 중 오류 발생: {e}")

def main():
    """메인 실행 함수"""
    print("🔍 PDF 직접 텍스트 추출기")
    print("="*40)
    
    # PDF 파일 경로 입력
    pdf_path = input("PDF 파일 경로를 입력하세요: ").strip()
    
    if not pdf_path:
        print("❌ PDF 파일 경로가 입력되지 않았습니다.")
        return
    
    try:
        # 텍스트 추출기 초기화
        extractor = PDFTextExtractor()
        
        # PDF에서 텍스트 추출
        results = extractor.extract_text(pdf_path)
        
        # 결과 출력
        extractor.display_results(results)
        
        # 저장 여부 확인
        if results['success']:
            save = input("\n💾 결과를 JSON 파일로 저장하시겠습니까? (y/n): ").lower().strip()
            if save == 'y':
                filename = input("파일명 (기본값: 자동생성): ").strip()
                if not filename:
                    filename = None
                extractor.save_results(results, filename)
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()
