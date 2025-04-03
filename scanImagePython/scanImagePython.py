import os
import sys
import cv2
import numpy as np
import shutil
import subprocess
from datetime import datetime
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
        self.is_expiration_date = False
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.layout = QVBoxLayout()
        
        self.image_label = QLabel("No image loaded")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedHeight(400)
        self.layout.addWidget(self.image_label)
        
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.layout.addWidget(self.text_output)
        
        self.load_button = QPushButton("Load Passport Image")
        self.load_button.clicked.connect(self.load_image)
        self.layout.addWidget(self.load_button)
        
        self.scan_button = QPushButton("Scan MRZ")
        self.scan_button.clicked.connect(self.scan_mrz)
        self.scan_button.setEnabled(False)
        self.layout.addWidget(self.scan_button)
        
        self.central_widget.setLayout(self.layout)
        
        self.current_image_path = None
        self.tesseract_path = self.find_tesseract()
        
        if not self.tesseract_path:
            self.show_tesseract_help()
        else:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path

    def find_tesseract(self):
        try:
            tesseract_path = shutil.which('tesseract')
            if tesseract_path:
                return tesseract_path
            if sys.platform == 'win32':
                common_paths = [
                    r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe',
                    r'C:\\Program Files (x86)\\Tesseract-OCR\\tesseract.exe'
                ]
                for path in common_paths:
                    if os.path.exists(path):
                        return path
            subprocess.run(['tesseract', '--version'], check=True, stdout=subprocess.PIPE)
            return 'tesseract'
        except:
            return None

    def show_tesseract_help(self):
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Tesseract Not Found")
        guide = (
            "1. Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "2. During installation, check 'Add to PATH' and install language data"
        )
        msg.setText(f"Tesseract OCR is required but not found.\n\n{guide}")
        msg.exec_()

    def load_image(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Passport Image", "", "Images (*.png *.jpg *.jpeg *.bmp)", options=options)
        if file_path:
            self.current_image_path = file_path
            pixmap = QPixmap(file_path)
            self.image_label.setPixmap(pixmap.scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio))
            self.scan_button.setEnabled(True)
            self.text_output.clear()

    def preprocess_image(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    def parse_mrz_date(self, mrz_date):
        if len(mrz_date) != 6 or not mrz_date.isdigit():
            return "Invalid date"
        if self.is_expiration_date:
            year = "20" + mrz_date[:2]
        else:
            current_year_short = int(str(datetime.now().year)[2:])
            year = "19" + mrz_date[:2] if int(mrz_date[:2]) > current_year_short else "20" + mrz_date[:2]
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
    
    def scan_mrz(self):
        if not self.current_image_path:
            return
        try:
            img = cv2.imread(self.current_image_path)
            processed_img = self.preprocess_image(img)
            temp_path = "temp_mrz.png"
            cv2.imwrite(temp_path, processed_img)
            mrz = read_mrz(temp_path, extra_cmdline_params='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<')
            os.remove(temp_path)
            if not mrz:
                self.text_output.setText("No MRZ detected. Please ensure the image is high quality and well-aligned.")
                return
            mrz_data = mrz.to_dict()
            result_text = "🛂 Passport MRZ Data:\n\n"
            surname = mrz_data.get('surname', 'Unknown')
            #given_names = mrz_data.get('given_names', 'Unknown')
            self.is_expiration_date = True
            expiration_date = self.parse_mrz_date(mrz_data.get('expiration_date', '000000'))
            self.is_expiration_date = False
            fields = [
                ('Document Type', 'P'),
                ('Issuing Country', mrz_data.get('country', 'Unknown')),
                ('Passport Number', mrz_data.get('number', 'Unknown')),
                ('Name', self.parse_mrz_name(mrz_data.get('names', 'Unknown'))),
                ('Surname', surname),
                ('Date of Birth', self.parse_mrz_date(mrz_data.get('date_of_birth', '000000'))),
                ('Expiration Date', expiration_date),
                ('Nationality', mrz_data.get('nationality', 'Unknown')),
                ('Gender', 'Male' if mrz_data.get('sex') == 'M' else 'Female')
            ]
            for field, value in fields:
                result_text += f"• {field}: {value}\n"
            self.text_output.setText(result_text)
            self.display_image(img)
        except Exception as e:
            self.text_output.setText(f"❌ Error: {str(e)}")

    def display_image(self, img):
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(q_img).scaled(self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportScannerApp()
    window.show()
    sys.exit(app.exec_())
