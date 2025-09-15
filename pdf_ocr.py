import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance, ImageFilter
import os
import sys
from typing import List, Dict
import json
import cv2
import numpy as np

class PDFOCR:
    def __init__(self, tesseract_path: str = None):
        """
        PDF OCR 분석기 초기화
        
        Args:
            tesseract_path: Tesseract 실행 파일 경로 (Windows에서 필요할 수 있음)
        """
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        
        # macOS에서 Tesseract 경로 설정 (필요시)
        if sys.platform == "darwin":
            # Homebrew로 설치된 경우
            possible_paths = [
                "/opt/homebrew/bin/tesseract",
                "/usr/local/bin/tesseract",
                "/usr/bin/tesseract"
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    pytesseract.pytesseract.tesseract_cmd = path
                    break
    
    def extract_text_from_pdf(self, pdf_path: str, language: str = 'kor+eng') -> Dict:
        """
        PDF에서 모든 텍스트를 추출합니다.
        
        Args:
            pdf_path: PDF 파일 경로
            language: OCR 언어 설정 (기본값: 'kor+eng')
        
        Returns:
            페이지별 텍스트와 전체 텍스트가 포함된 딕셔너리
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
        
        print(f"📄 PDF 파일 분석 중: {os.path.basename(pdf_path)}")
        print(f"🌐 언어 설정: {language}")
        
        try:
            # PDF를 이미지로 변환
            print("🔄 PDF를 이미지로 변환 중...")
            pages = convert_from_path(pdf_path, dpi=300)  # 높은 DPI로 더 정확한 OCR
            print(f"✅ {len(pages)}개 페이지 변환 완료")
            
            results = {
                'file_name': os.path.basename(pdf_path),
                'total_pages': len(pages),
                'pages': [],
                'full_text': '',
                'extraction_info': {
                    'language': language,
                    'dpi': 300,
                    'total_characters': 0,
                    'total_words': 0
                }
            }
            
            # 각 페이지별로 OCR 수행
            for i, page in enumerate(pages, 1):
                print(f"🔍 페이지 {i}/{len(pages)} OCR 처리 중...")
                
                # 이미지 전처리
                processed_page = self._preprocess_image(page)
                
                # OCR 설정 최적화 (여러 설정 시도)
                configs = [
                    r'--oem 3 --psm 6',  # 기본 설정
                    r'--oem 3 --psm 3',  # 자동 페이지 분할
                    r'--oem 3 --psm 4',  # 단일 컬럼 텍스트
                    r'--oem 3 --psm 1',  # 자동 페이지 분할 + OSD
                ]
                
                # 여러 설정으로 OCR 시도
                best_text = ""
                best_score = 0
                
                for config in configs:
                    try:
                        temp_text = pytesseract.image_to_string(processed_page, lang=language, config=config)
                        # 텍스트 품질 점수 계산 (한글과 영어 비율)
                        korean_chars = sum(1 for c in temp_text if '가' <= c <= '힣')
                        english_chars = sum(1 for c in temp_text if c.isalpha() and ord(c) < 128)
                        total_chars = len(temp_text.replace(' ', '').replace('\n', ''))
                        
                        if total_chars > 0:
                            score = (korean_chars + english_chars) / total_chars
                            if score > best_score:
                                best_score = score
                                best_text = temp_text
                    except:
                        continue
                
                # 최고 점수 텍스트 사용
                text = best_text if best_text else pytesseract.image_to_string(processed_page, lang=language)
                
                # 텍스트 정리
                cleaned_text = self._clean_text(text)
                
                # 페이지 정보 저장
                page_info = {
                    'page_number': i,
                    'raw_text': text,
                    'cleaned_text': cleaned_text,
                    'character_count': len(cleaned_text),
                    'word_count': len(cleaned_text.split()) if cleaned_text else 0
                }
                
                results['pages'].append(page_info)
                results['full_text'] += cleaned_text + '\n\n'
                
                print(f"   ✅ 페이지 {i}: {page_info['word_count']}단어, {page_info['character_count']}문자")
            
            # 전체 통계 계산
            results['extraction_info']['total_characters'] = len(results['full_text'])
            results['extraction_info']['total_words'] = len(results['full_text'].split())
            
            print(f"\n📊 추출 완료!")
            print(f"   📄 총 페이지: {results['total_pages']}")
            print(f"   📝 총 단어: {results['extraction_info']['total_words']}")
            print(f"   📝 총 문자: {results['extraction_info']['total_characters']}")
            
            return results
            
        except Exception as e:
            print(f"❌ OCR 처리 중 오류 발생: {e}")
            raise
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """고급 이미지 전처리를 통한 OCR 성능 개선"""
        try:
            # PIL Image를 OpenCV 형식으로 변환
            img_array = np.array(image)
            
            # 그레이스케일 변환
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            
            # 1. 노이즈 제거 (가우시안 블러)
            denoised = cv2.GaussianBlur(gray, (3, 3), 0)
            
            # 2. 대비 향상 (CLAHE)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
            enhanced = clahe.apply(denoised)
            
            # 3. 적응적 이진화 (더 정확한 텍스트 인식)
            binary = cv2.adaptiveThreshold(enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # 4. 모폴로지 연산으로 노이즈 제거
            kernel = np.ones((2,2), np.uint8)
            cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            # 5. 텍스트 선명화
            kernel_sharpen = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(cleaned, -1, kernel_sharpen)
            
            # 6. 크기 조정 (더 큰 이미지로)
            height, width = sharpened.shape
            if height < 1000:  # 너무 작으면 확대
                scale_factor = 1000 / height
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                resized = cv2.resize(sharpened, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
            else:
                resized = sharpened
            
            # 다시 PIL Image로 변환
            processed_image = Image.fromarray(resized)
            
            return processed_image
            
        except Exception as e:
            print(f"⚠️ 이미지 전처리 중 오류 발생: {e}")
            return image  # 전처리 실패시 원본 반환
    
    def _clean_text(self, text: str) -> str:
        """텍스트를 정리합니다."""
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
    
    def save_results(self, results: Dict, output_file: str = None):
        """결과를 JSON 파일로 저장합니다."""
        if not output_file:
            base_name = os.path.splitext(results['file_name'])[0]
            output_file = f"{base_name}_ocr_results.json"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"💾 결과가 {output_file}에 저장되었습니다.")
        except Exception as e:
            print(f"❌ 파일 저장 중 오류 발생: {e}")
    
    def display_results(self, results: Dict, show_pages: bool = True):
        """결과를 콘솔에 출력합니다."""
        print("\n" + "="*60)
        print("📄 PDF OCR 추출 결과")
        print("="*60)
        
        print(f"📁 파일명: {results['file_name']}")
        print(f"📄 총 페이지: {results['total_pages']}")
        print(f"📝 총 단어: {results['extraction_info']['total_words']}")
        print(f"📝 총 문자: {results['extraction_info']['total_characters']}")
        print(f"🌐 언어: {results['extraction_info']['language']}")
        
        if show_pages:
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

def main():
    """메인 실행 함수"""
    print("🔍 PDF OCR 텍스트 추출기")
    print("="*40)
    
    # PDF 파일 경로 입력
    pdf_path = input("PDF 파일 경로를 입력하세요: ").strip()
    
    if not pdf_path:
        print("❌ PDF 파일 경로가 입력되지 않았습니다.")
        return
    
    # 언어 설정
    print("\n언어를 선택하세요:")
    print("1. 한국어 + 영어 (기본값)")
    print("2. 한국어만")
    print("3. 영어만")
    print("4. 일본어 + 영어")
    print("5. 중국어 + 영어")
    
    lang_choice = input("선택 (1-5, 기본값: 1): ").strip()
    
    language_map = {
        "1": "kor+eng",
        "2": "kor",
        "3": "eng", 
        "4": "jpn+eng",
        "5": "chi_sim+eng"
    }
    
    selected_language = language_map.get(lang_choice, "kor+eng")
    
    try:
        # OCR 분석기 초기화
        ocr = PDFOCR()
        
        # PDF에서 텍스트 추출
        results = ocr.extract_text_from_pdf(pdf_path, selected_language)
        
        # 결과 출력
        ocr.display_results(results)
        
        # 저장 여부 확인
        save = input("\n💾 결과를 JSON 파일로 저장하시겠습니까? (y/n): ").lower().strip()
        if save == 'y':
            filename = input("파일명 (기본값: 자동생성): ").strip()
            if not filename:
                filename = None
            ocr.save_results(results, filename)
        
    except FileNotFoundError as e:
        print(f"❌ {e}")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    main()
