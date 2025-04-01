import os
import sys
import cv2
import numpy as np
import shutil
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QWidget, QFileDialog, QTextEdit, QMessageBox
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
from passporteye import read_mrz
import pytesseract

class PassportScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Passport MRZ Scanner")
        self.setGeometry(100, 100, 800, 600)
        self.is_expiration_date = False  # Flag for date parsing
        
        # Central Widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Layout
        self.layout = QVBoxLayout()
        
        # Image Label
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedHeight(400)
        self.layout.addWidget(self.image_label)
        
        # Text Output
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.layout.addWidget(self.text_output)
        
        # Buttons
        self.load_button = QPushButton("Load Passport Image")
        self.load_button.clicked.connect(self.load_image)
        self.layout.addWidget(self.load_button)
        
        self.scan_button = QPushButton("Scan MRZ")
        self.scan_button.clicked.connect(self.scan_mrz)
        self.scan_button.setEnabled(False)
        self.layout.addWidget(self.scan_button)
        
        # Set layout
        self.central_widget.setLayout(self.layout)
        
        # Variables
        self.current_image_path = None
        self.tesseract_path = self.find_tesseract()
        
        if not self.tesseract_path:
            self.show_tesseract_help()
        else:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path

    def find_tesseract(self):
        """Find Tesseract executable path."""
        try:
            # Check PATH first
            tesseract_path = shutil.which('tesseract')
            if tesseract_path:
                return tesseract_path
            
            # Common Windows paths
            if sys.platform == 'win32':
                common_paths = [
                    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        return path
            
            # Try direct version check
            subprocess.run(['tesseract', '--version'], check=True, stdout=subprocess.PIPE)
            return 'tesseract'
        except:
            return None

    def show_tesseract_help(self):
        """Show Tesseract installation instructions."""
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Tesseract Not Found")
        
        if sys.platform == 'win32':
            guide = (
                "1. Download Tesseract from:\n"
                "   https://github.com/UB-Mannheim/tesseract/wiki\n\n"
                "2. During installation:\n"
                "   - Check 'Add to PATH'\n"
                "   - Install language data"
            )
        else:
            guide = (
                "Run in terminal:\n"
                "sudo apt install tesseract-ocr  # Linux\n"
                "brew install tesseract         # macOS"
            )
        
        msg.setText(
            f"Tesseract OCR is required but not found.\n\n"
            f"Installation Guide:\n{guide}"
        )
        msg.exec_()

    def load_image(self):
        """Load passport image."""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Passport Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp)", options=options
        )
        
        if file_path:
            self.current_image_path = file_path
            pixmap = QPixmap(file_path)
            self.image_label.setPixmap(
                pixmap.scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio)
            )
            self.scan_button.setEnabled(True)
            self.text_output.clear()

    def preprocess_image(self, img):
        """Enhance image for better OCR."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def parse_mrz_date(self, mrz_date):
        """Convert YYMMDD to DD/MM/YYYY with proper century handling."""
        if len(mrz_date) != 6 or not mrz_date.isdigit():
            return "Invalid date"
        
        # For expiration dates (assume 21st century if year < 30)
        if self.is_expiration_date:
            year = "20" + mrz_date[:2] if int(mrz_date[:2]) < 30 else "19" + mrz_date[:2]
        # For birth dates (assume 20th century if year > 30)
        else:
            year = "19" + mrz_date[:2] if int(mrz_date[:2]) > 30 else "20" + mrz_date[:2]
        
        return f"{mrz_date[4:6]}/{mrz_date[2:4]}/{year}"

    def parse_mrz_name(self, mrz_name):
        """Convert MRZ name format (SURNAME<GIVENNAMES) to normal format."""
        if not mrz_name or not isinstance(mrz_name, str):
            return "Unknown"
        
        try:
            if '<' in mrz_name:
                parts = [part.strip() for part in mrz_name.split('<') if part.strip()]
                if len(parts) >= 2:
                    # Return "GIVENNAME SURNAME" format
                    return f"{parts[1]} {parts[0]}"
                return parts[0] if parts else "Unknown"
            return mrz_name
        except Exception as e:
            print(f"Error parsing name: {e}")
            return mrz_name

    def highlight_mrz_area(self, img, mrz):
        """Highlight MRZ area with compatibility for different PassportEye versions."""
        try:
            # For PassportEye 2.0+ (using aux dictionary)
            if hasattr(mrz, 'aux') and 'text_annotations' in mrz.aux:
                vertices = mrz.aux['text_annotations'][0]['bounding_poly']['vertices']
                points = [(v['x'], v['y']) for v in vertices]
                cv2.polylines(img, [np.array(points, np.int32)], True, (0, 255, 0), 2)
                cv2.putText(img, "MRZ", (points[0][0], points[0][1]-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            # For older versions or fallback
            elif hasattr(mrz, 'line_y') and hasattr(mrz, 'line_length'):
                height, width = img.shape[:2]
                y = int(mrz.line_y * height)
                length = int(mrz.line_length * width)
                cv2.rectangle(img, (0, y-20), (length, y+30), (0, 255, 0), 2)
                cv2.putText(img, "MRZ", (10, y-25), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            return img
            
        except Exception as e:
            print(f"MRZ highlighting error: {e}")
            return img

    def scan_mrz(self):
        """Extract MRZ from passport image with proper formatting."""
        if not self.current_image_path:
            return
            
        try:
            img = cv2.imread(self.current_image_path)
            processed_img = self.preprocess_image(img)
            
            # Save temp image
            temp_path = "temp_mrz.png"
            cv2.imwrite(temp_path, processed_img)
            
            # Read MRZ with optimized parameters
            mrz = read_mrz(
                temp_path,
                extra_cmdline_params='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<'
            )
            os.remove(temp_path)
            
            if not mrz:
                self.text_output.setText("No MRZ detected. Please ensure:\n"
                                      "- The MRZ is clearly visible\n"
                                      "- The image is high quality\n"
                                      "- The passport is properly aligned")
                return
                
            # Process MRZ data with proper formatting
            mrz_data = mrz.to_dict()
            result_text = "🛂 Passport MRZ Data:\n\n"
            
            # Format important fields correctly
            self.is_expiration_date = True
            expiration_date = self.parse_mrz_date(mrz_data.get('expiration_date', '000000'))
            self.is_expiration_date = False
            
            fields = [
                ('Document Type', mrz_data.get('type', 'Unknown')),
                ('Issuing Country', mrz_data.get('country', 'Unknown')),
                ('Passport Number', mrz_data.get('number', 'Unknown')),
                ('Date of Birth', self.parse_mrz_date(mrz_data.get('date_of_birth', '000000'))),
                ('Expiration Date', expiration_date),
                ('Nationality', mrz_data.get('nationality', 'Unknown')),
                ('Gender', 'Male' if mrz_data.get('sex') == 'M' else 'Female'),
                ('Full Name', self.parse_mrz_name(mrz_data.get('names', 'Unknown')))
            ]
            
            for field, value in fields:
                result_text += f"• {field}: {value}\n"
            
            self.text_output.setText(result_text)
            
            # Highlight and display image
            img = self.highlight_mrz_area(img, mrz)
            self.display_image(img)
            
        except Exception as e:
            self.text_output.setText(
                f"❌ Error: {str(e)}\n\n"
                "Troubleshooting:\n"
                "1. Ensure passport MRZ is clearly visible\n"
                "2. Try a higher-quality image\n"
                "3. Verify Tesseract is properly installed"
            )

    def display_image(self, img):
        """Convert OpenCV image to QPixmap and display."""
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(q_img).scaled(
            self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportScannerApp()
    window.show()
    sys.exit(app.exec_())