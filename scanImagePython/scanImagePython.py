import os
import sys
import cv2
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton,
    QVBoxLayout, QWidget, QFileDialog, QTextEdit, QMessageBox
)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt
from passporteye import read_mrz
import pytesseract  # Fallback if PassportEye fails

class PassportScannerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Passport MRZ Scanner")
        self.setGeometry(100, 100, 800, 600)
        
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
            print(f"Tesseract found at: {self.tesseract_path}")
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path  # Set for pytesseract

    def find_tesseract(self):
        """Find Tesseract executable path."""
        try:
            # Check PATH first
            tesseract_path = shutil.which('tesseract')
            if tesseract_path:
                return tesseract_path
            
            # Common Windows paths
            if sys.platform == 'win32':
                paths = [
                    r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                    r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
                ]
                for path in paths:
                    if os.path.exists(path):
                        return path
            
            # Try direct version check
            subprocess.run(['tesseract', '--version'], check=True, stdout=subprocess.PIPE)
            return 'tesseract'  # Found in PATH but shutil missed it
        except:
            return None

    def show_tesseract_help(self):
        """Show Tesseract installation guide."""
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
            f"Installation Guide:\n{guide}\n\n"
            f"Current PATH:\n{os.environ.get('PATH', '')}"
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

    def scan_mrz(self):
        """Extract MRZ from passport image."""
        if not self.current_image_path:
            return
            
        try:
            # Read and preprocess image
            img = cv2.imread(self.current_image_path)
            processed_img = self.preprocess_image(img)
            
            # Save temp image
            temp_path = "temp_mrz.png"
            cv2.imwrite(temp_path, processed_img)
            
            # Try PassportEye first
            mrz = read_mrz(
                temp_path,
                extra_cmdline_params='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<'
            )
            
            # Fallback to pytesseract if PassportEye fails
            if not mrz:
                mrz_text = pytesseract.image_to_string(
                    processed_img,
                    config='--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<'
                )
                self.text_output.setText(f"MRZ (Fallback):\n{mrz_text}")
            else:
                mrz_data = mrz.to_dict()
                result = "\n".join([f"{k}: {v}" for k, v in mrz_data.items()])
                self.text_output.setText(f"MRZ Data:\n{result}")
                
                # Highlight MRZ area
                self.highlight_mrz_area(img, mrz.rect)
            
            os.remove(temp_path)  # Clean up
            
        except Exception as e:
            self.text_output.setText(
                f"❌ Error: {str(e)}\n\n"
                "Troubleshooting:\n"
                "1. Ensure passport MRZ is visible\n"
                "2. Try a higher-quality image\n"
                "3. Verify Tesseract is installed"
            )

    def highlight_mrz_area(self, img, rect):
        """Draw rectangle around MRZ zone."""
        x, y, w, h = rect.x, rect.y, rect.width, rect.height
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(img, "MRZ", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Convert to QPixmap
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = img_rgb.shape
        bytes_per_line = ch * w
        q_img = QImage(img_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
        self.image_label.setPixmap(QPixmap.fromImage(q_img).scaled(
            self.image_label.width(), self.image_label.height(), Qt.KeepAspectRatio)
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PassportScannerApp()
    window.show()
    sys.exit(app.exec_())