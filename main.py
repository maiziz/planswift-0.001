import sys
import fitz  # PyMuPDF
import math
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QHBoxLayout, QLabel, QPushButton, QFileDialog, QScrollArea,
                           QInputDialog, QMessageBox, QComboBox, QTreeWidget, 
                           QTreeWidgetItem, QTabWidget, QGroupBox, QFormLayout,
                           QLineEdit, QSpinBox, QDoubleSpinBox, QRadioButton,
                           QButtonGroup, QDialog, QCheckBox)
from PyQt5.QtCore import Qt, QPointF, QRectF, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QIcon, QCursor
import gc

class Magnifier(QLabel):
    def __init__(self, parent, zoom_factor=2.5):
        super().__init__(parent)
        self.parent = parent
        self.zoom_factor = zoom_factor
        self.size = 100  
        self.setFixedSize(self.size, self.size)
        self.setMouseTracking(True)
        self.hide()
        self.setStyleSheet("""
            background-color: rgba(255, 255, 255, 20);
            border: 2px solid red;
            border-radius: 50px;
        """)

    def update_magnifier(self, pos, source_pixmap, force_show=False):
        try:
            if source_pixmap and not source_pixmap.isNull():
                source_size = self.size / self.zoom_factor
                padding = source_size * 0.1  
                
                doc_pos = self.parent.mapFromGlobal(QCursor.pos())
                
                x = doc_pos.x() - (source_size + padding) / 2
                y = doc_pos.y() - (source_size + padding) / 2
                
                source_rect = QRectF(x, y, source_size + padding, source_size + padding)
                target_rect = QRectF(0, 0, self.size, self.size)
                
                result = QPixmap(self.size, self.size)
                result.fill(Qt.transparent)
                
                painter = QPainter(result)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                
                painter.drawPixmap(target_rect, source_pixmap, source_rect)
                
                center = QPoint(self.size//2, self.size//2)
                
                painter.setPen(QPen(QColor(255, 0, 0, 80), 3))
                painter.drawEllipse(center, self.size//2 - 4, self.size//2 - 4)
                
                painter.setPen(QPen(Qt.red, 2))
                painter.drawLine(center.x(), center.y() - 20, center.x(), center.y() + 20)
                painter.drawLine(center.x() - 20, center.y(), center.x() + 20, center.y())
                
                painter.setPen(QPen(QColor(255, 0, 0, 60), 1))
                for radius in [25, 50, 75]:
                    painter.drawEllipse(center, radius, radius)
                
                painter.end()
                self.setPixmap(result)
                
                screen_pos = self.parent.mapToGlobal(doc_pos)
                parent_rect = self.parent.rect()
                
                mag_x = doc_pos.x() + 30
                mag_y = doc_pos.y() - self.size//2
                
                if mag_x + self.size > parent_rect.width():
                    mag_x = doc_pos.x() - self.size - 30
                
                if mag_y < 0:
                    mag_y = 0
                elif mag_y + self.size > parent_rect.height():
                    mag_y = parent_rect.height() - self.size
                
                self.move(mag_x, mag_y)
                if force_show:
                    self.show()
                    self.raise_()
                    
        except Exception as e:
            print(f"Error updating magnifier: {str(e)}")
            self.hide()

    def cleanup(self):
        try:
            self.hide()
            self.setPixmap(QPixmap())
        except Exception as e:
            print(f"Error cleaning up magnifier: {str(e)}")

class MeasurementItem:
    def __init__(self, type_name, value, unit, description=""):
        self.type = type_name
        self.value = value
        self.unit = unit
        self.description = description

    def __str__(self):
        return f"{self.type}: {self.value:.2f} {self.unit} - {self.description}"

class DrawingLayer:
    def __init__(self, name, color=QColor('blue')):
        self.name = name
        self.color = color
        self.visible = True
        self.measurements = []

class QuantityEstimator(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Initialize drawing layers first
        self.layers = {
            'Calibration': DrawingLayer('Calibration', QColor(0, 150, 0)),  # Green
            'Distance': DrawingLayer('Distance', QColor(0, 0, 255)),  # Blue
            'Area': DrawingLayer('Area', QColor(255, 0, 0))  # Red
        }
        self.active_layer = 'Distance'  # Default active layer
        
        # Initialize other attributes
        self.current_pdf = None
        self.current_page = 0
        self.scale_factor = 1.0
        self.scale_calibration = 1.0
        self.measurement_mode = None
        self.measurement_points = []
        self.measurements = []
        self.current_measurement = None
        self.drawing = False
        self.current_description = ""
        self.magnifier = None
        self.orientation = 0
        self.known_scale = None
        self.current_pixmap = None
        self.calibration_in_progress = False
        self.show_magnifier = False
        self.last_mouse_pos = None
        
        # Initialize UI after all attributes
        self.initUI()
        self.setWindowTitle('Quantity Estimator')
        self.setGeometry(100, 100, 1400, 800)

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Create sidebar
        sidebar = QWidget()
        sidebar.setMaximumWidth(300)
        sidebar.setMinimumWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)

        # Project Information
        project_group = QGroupBox("Project Information")
        project_layout = QFormLayout()
        self.project_name = QLineEdit()
        self.project_number = QLineEdit()
        project_layout.addRow("Project Name:", self.project_name)
        project_layout.addRow("Project Number:", self.project_number)
        project_group.setLayout(project_layout)
        sidebar_layout.addWidget(project_group)

        # Tools Group
        tools_group = QGroupBox("Measurement Tools")
        tools_layout = QVBoxLayout()

        # Calibration Group
        calibration_group = QGroupBox("Scale Calibration")
        calibration_layout = QVBoxLayout()
        
        scale_layout = QHBoxLayout()
        self.scale_value = QDoubleSpinBox()
        self.scale_value.setRange(0.1, 1000)
        self.scale_value.setValue(1.0)
        self.scale_unit = QComboBox()
        self.scale_unit.addItems(['1/4"=1\'', '1/8"=1\'', '1/16"=1\'', '3/32"=1\'', 'Custom'])
        scale_layout.addWidget(QLabel("Scale:"))
        scale_layout.addWidget(self.scale_value)
        scale_layout.addWidget(self.scale_unit)
        
        self.calibrate_button = QPushButton('Calibrate Scale')
        self.calibrate_button.clicked.connect(self.start_calibration)
        
        calibration_layout.addLayout(scale_layout)
        calibration_layout.addWidget(self.calibrate_button)
        calibration_group.setLayout(calibration_layout)
        tools_layout.addWidget(calibration_group)

        # Orientation Group
        orientation_group = QGroupBox("Page Orientation")
        orientation_layout = QHBoxLayout()
        
        self.portrait_btn = QRadioButton("Portrait")
        self.landscape_right_btn = QRadioButton("Landscape →")
        self.landscape_left_btn = QRadioButton("Landscape ←")
        
        self.orientation_group = QButtonGroup()
        self.orientation_group.addButton(self.portrait_btn)
        self.orientation_group.addButton(self.landscape_right_btn)
        self.orientation_group.addButton(self.landscape_left_btn)
        
        self.portrait_btn.setChecked(True)
        
        orientation_layout.addWidget(self.portrait_btn)
        orientation_layout.addWidget(self.landscape_right_btn)
        orientation_layout.addWidget(self.landscape_left_btn)
        
        self.orientation_group.buttonClicked.connect(self.change_orientation)
        orientation_group.setLayout(orientation_layout)
        tools_layout.addWidget(orientation_group)

        # Measurement Type
        self.measurement_type = QComboBox()
        self.measurement_type.addItems(['None', 'Distance', 'Area', 'Count'])
        self.measurement_type.currentTextChanged.connect(self.change_measurement_mode)

        description_layout = QFormLayout()
        self.description_input = QLineEdit()
        description_layout.addRow("Description:", self.description_input)

        tools_layout.addWidget(QLabel("Measurement Type:"))
        tools_layout.addWidget(self.measurement_type)
        tools_layout.addLayout(description_layout)
        tools_group.setLayout(tools_layout)
        sidebar_layout.addWidget(tools_group)

        # Measurements Group
        measurements_group = QGroupBox("Measurements")
        measurements_layout = QVBoxLayout()
        self.measurements_tree = QTreeWidget()
        self.measurements_tree.setHeaderLabels(['Type', 'Value', 'Description'])
        self.measurements_tree.setColumnCount(3)
        measurements_layout.addWidget(self.measurements_tree)
        measurements_group.setLayout(measurements_layout)
        sidebar_layout.addWidget(measurements_group)

        # Layer Controls
        layer_group = QGroupBox("Layers")
        layer_layout = QVBoxLayout()
        
        self.layer_controls = {}
        for layer_name, layer in self.layers.items():
            layer_widget = QWidget()
            layer_h_layout = QHBoxLayout()
            layer_widget.setLayout(layer_h_layout)
            
            # Visibility checkbox
            visibility_cb = QCheckBox()
            visibility_cb.setChecked(True)
            visibility_cb.stateChanged.connect(lambda state, name=layer_name: self.toggle_layer_visibility(name, state))
            
            # Color indicator
            color_btn = QPushButton()
            color_btn.setFixedSize(20, 20)
            color_btn.setStyleSheet(f"background-color: {layer.color.name()}; border: none;")
            color_btn.clicked.connect(lambda checked, name=layer_name: self.change_layer_color(name))
            
            # Layer name label
            name_label = QLabel(layer_name)
            
            layer_h_layout.addWidget(visibility_cb)
            layer_h_layout.addWidget(color_btn)
            layer_h_layout.addWidget(name_label)
            layer_h_layout.addStretch()
            
            self.layer_controls[layer_name] = {
                'widget': layer_widget,
                'checkbox': visibility_cb,
                'color_btn': color_btn
            }
            layer_layout.addWidget(layer_widget)
        
        layer_group.setLayout(layer_layout)
        sidebar_layout.addWidget(layer_group)

        main_layout.addWidget(sidebar)

        # Content Area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # Toolbar
        toolbar = QHBoxLayout()
        
        self.load_button = QPushButton('Load PDF')
        self.load_button.clicked.connect(self.load_pdf)
        
        self.zoom_in_button = QPushButton('Zoom In')
        self.zoom_in_button.clicked.connect(self.zoom_in)
        
        self.zoom_out_button = QPushButton('Zoom Out')
        self.zoom_out_button.clicked.connect(self.zoom_out)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.valueChanged.connect(self.change_page)

        toolbar.addWidget(self.load_button)
        toolbar.addWidget(self.zoom_in_button)
        toolbar.addWidget(self.zoom_out_button)
        toolbar.addWidget(QLabel("Page:"))
        toolbar.addWidget(self.page_spin)
        toolbar.addStretch()

        content_layout.addLayout(toolbar)

        # PDF Display Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)

        self.pdf_label = QLabel()
        self.pdf_label.setAlignment(Qt.AlignCenter)
        self.pdf_label.setMouseTracking(True)
        self.scroll_area.setWidget(self.pdf_label)

        self.magnifier = Magnifier(self.pdf_label)
        
        self.pdf_label.mousePressEvent = self.on_mouse_press
        self.pdf_label.mouseMoveEvent = self.on_mouse_move
        self.pdf_label.mouseReleaseEvent = self.on_mouse_release

        content_layout.addWidget(self.scroll_area)
        main_layout.addWidget(content_widget)

    def closeEvent(self, event):
        try:
            if self.magnifier:
                self.magnifier.cleanup()
            if self.current_pdf:
                self.current_pdf.close()
            event.accept()
        except Exception as e:
            print(f"Error in closeEvent: {str(e)}")
            event.accept()

    def change_page(self, value):
        if self.current_pdf:
            self.current_page = value - 1
            self.display_page()

    def add_measurement_to_list(self, measurement_type, value, unit, description=""):
        try:
            if not description:
                description = f"{measurement_type} {len(self.measurements) + 1}"
            
            # Create measurement item with points
            measurement = MeasurementItem(measurement_type, value, unit, description)
            measurement.points = self.measurement_points.copy()  # Store points for drawing
            
            # Add to appropriate layer
            layer_name = measurement_type if measurement_type in self.layers else 'Distance'
            self.layers[layer_name].measurements.append(measurement)
            self.measurements.append(measurement)
            
            # Add to tree widget with layer color
            item = QTreeWidgetItem(self.measurements_tree)
            item.setText(0, measurement_type)
            item.setText(1, f"{value:.2f} {unit}")
            item.setText(2, description)
            
            layer_color = self.layers[layer_name].color
            for col in range(3):
                item.setBackground(col, QColor(layer_color.red(), layer_color.green(), layer_color.blue(), 30))
            
            self.measurements_tree.resizeColumnToContents(0)
            self.measurements_tree.resizeColumnToContents(1)
            self.measurements_tree.resizeColumnToContents(2)
            
            self.description_input.clear()
            
        except Exception as e:
            print(f"Error adding measurement to list: {str(e)}")

    def load_pdf(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open PDF File", "", "PDF Files (*.pdf)")
        
        if file_name:
            try:
                self.current_pdf = fitz.open(file_name)
                self.current_page = 0
                self.page_spin.setMaximum(len(self.current_pdf))
                self.page_spin.setValue(1)
                self.display_page()
            except Exception as e:
                print(f"Error loading PDF: {str(e)}")
                QMessageBox.warning(self, "Error", "Failed to load PDF")

    def start_calibration(self):
        try:
            if not self.current_pdf:
                QMessageBox.warning(self, "Warning", "Please load a PDF first")
                return
                
            scale_text = self.scale_unit.currentText()
            
            if scale_text:
                scale_value = self.parse_architectural_scale(scale_text)
                self.known_scale = scale_value
            else:
                self.known_scale = self.scale_value.value()
            
            self.measurement_mode = "calibration"
            self.calibration_in_progress = True
            self.measurement_points = []
            self.show_magnifier = True
            
            if self.magnifier:
                self.magnifier.cleanup()
            self.magnifier = Magnifier(self.pdf_label, zoom_factor=2.5)
            
        except Exception as e:
            print(f"Error starting calibration: {str(e)}")
            self.cleanup_calibration()

    def on_mouse_move(self, event):
        try:
            if not self.pdf_label.pixmap() or self.pdf_label.pixmap().isNull():
                return
                
            self.last_mouse_pos = event.pos()  
            pos = event.pos()
            
            if self.show_magnifier and self.magnifier and self.current_pixmap:
                viewport_pos = self.pdf_label.mapFromGlobal(QCursor.pos())
                self.magnifier.update_magnifier(viewport_pos, self.current_pixmap, force_show=True)
                
            if self.drawing and self.measurement_mode == "area":
                self.current_measurement = pos
                self.display_page()
                
        except Exception as e:
            print(f"Error in mouse move: {str(e)}")

    def on_mouse_press(self, event):
        if not self.measurement_mode and not self.calibration_in_progress:
            return

        try:
            if event.button() == Qt.LeftButton:
                pos = event.pos()
                if self.measurement_mode == "calibration":
                    self.measurement_points.append(pos)
                    if len(self.measurement_points) == 2:
                        self.display_page()  # Show line
                        self.prompt_for_distance()  # Ask for distance
                elif self.measurement_mode == "distance":
                    self.measurement_points.append(pos)
                    if len(self.measurement_points) == 2:
                        self.calculate_distance()
                        
        except Exception as e:
            print(f"Error in mouse press: {str(e)}")

    def prompt_for_distance(self):
        try:
            pixels = ((self.measurement_points[1].x() - self.measurement_points[0].x()) ** 2 +
                     (self.measurement_points[1].y() - self.measurement_points[0].y()) ** 2) ** 0.5
            
            distance, ok = QInputDialog.getDouble(self, "Enter Distance",
                "Enter the actual distance (in feet):", 1, 0, 1000, 2)
            
            if ok:
                self.scale_calibration = pixels / distance
                self.scale_value.setValue(distance)
                
                calibration_desc = f"Calibration Line ({distance:.2f} ft)"
                self.add_measurement_to_list("Calibration", distance, "feet", calibration_desc)
                
                QMessageBox.information(self, "Calibration Complete", 
                    f"Scale set to {distance:.2f} feet per {pixels:.2f} pixels")
            else:
                self.measurement_points = []
                
        except Exception as e:
            print(f"Error in distance input: {str(e)}")
            self.scale_calibration = 1.0
        finally:
            self.cleanup_calibration()

    def on_mouse_release(self, event):
        try:
            if self.drawing and self.measurement_mode == "area":
                self.measurement_points.append(event.pos())
                self.current_measurement = None
                if len(self.measurement_points) >= 3:
                    self.calculate_area()
                self.display_page()
        except Exception as e:
            print(f"Error in mouse release: {str(e)}")

    def complete_calibration(self):
        try:
            if len(self.measurement_points) != 2:
                return
                
            pixels = ((self.measurement_points[1].x() - self.measurement_points[0].x()) ** 2 +
                     (self.measurement_points[1].y() - self.measurement_points[0].y()) ** 2) ** 0.5
            
            if self.known_scale:
                self.scale_calibration = pixels / self.known_scale
                QMessageBox.information(self, "Calibration Complete", 
                    f"Scale set to {self.known_scale:.2f} feet per {pixels:.2f} pixels")
            else:
                try:
                    distance, ok = QInputDialog.getDouble(self, "Enter Distance",
                        "Enter the actual distance (in feet):", 1, 0, 1000, 2)
                    if ok:
                        self.scale_calibration = pixels / distance
                        QMessageBox.information(self, "Calibration Complete", 
                            f"Scale set to {distance:.2f} feet per {pixels:.2f} pixels")
                except Exception as e:
                    print(f"Error in distance input: {str(e)}")
                    self.scale_calibration = 1.0
            
        except Exception as e:
            print(f"Error completing calibration: {str(e)}")
            self.scale_calibration = 1.0
        finally:
            self.cleanup_calibration()

    def cleanup_calibration(self):
        try:
            self.measurement_mode = None
            self.measurement_points = []
            self.calibration_in_progress = False
            self.show_magnifier = False
            if self.magnifier:
                self.magnifier.cleanup()
            self.display_page()
        except Exception as e:
            print(f"Error in cleanup_calibration: {str(e)}")

    def keyPressEvent(self, event):
        try:
            if event.key() == Qt.Key_Escape:
                self.cleanup_calibration()
        except Exception as e:
            print(f"Error in keyPressEvent: {str(e)}")

    def change_measurement_mode(self, mode):
        self.measurement_mode = mode.lower() if mode != 'None' else None
        self.measurement_points = []
        self.current_measurement = None
        self.display_page()

    def calculate_distance(self):
        try:
            if len(self.measurement_points) != 2:
                return
            
            pixels = ((self.measurement_points[1].x() - self.measurement_points[0].x()) ** 2 +
                     (self.measurement_points[1].y() - self.measurement_points[0].y()) ** 2) ** 0.5
            
            if self.scale_calibration:
                feet = pixels / self.scale_calibration
                description = self.description_input.text()
                self.add_measurement_to_list("Distance", feet, "feet", description)
                
                self.display_page()
                
            self.measurement_points = []
                
        except Exception as e:
            print(f"Error in calculate_distance: {str(e)}")
            self.measurement_points = []
            self.display_page()

    def calculate_area(self):
        if len(self.measurement_points) < 3:
            return

        area = 0
        for i in range(len(self.measurement_points)):
            j = (i + 1) % len(self.measurement_points)
            area += self.measurement_points[i].x() * self.measurement_points[j].y()
            area -= self.measurement_points[j].x() * self.measurement_points[i].y()
        area = abs(area) / 2

        square_feet = area / (self.scale_calibration ** 2)
        self.add_measurement_to_list("Area", square_feet, "sq.ft")
        QMessageBox.information(self, "Area", f"Area: {square_feet:.2f} square feet")
        self.drawing = False
        self.measurement_points = []

    def change_orientation(self, button):
        if button == self.portrait_btn:
            self.orientation = 0
        elif button == self.landscape_right_btn:
            self.orientation = 90
        else:
            self.orientation = -90
        self.display_page()

    def parse_architectural_scale(self, scale_text):
        fraction = scale_text.split('=')[0].strip('"')
        if '/' in fraction:
            num, denom = fraction.split('/')
            return 12.0 * float(denom) / float(num)
        return float(fraction) * 12.0

    def toggle_layer_visibility(self, layer_name, state):
        self.layers[layer_name].visible = bool(state)
        self.display_page()

    def change_layer_color(self, layer_name):
        color = QColorDialog.getColor(self.layers[layer_name].color, self)
        if color.isValid():
            self.layers[layer_name].color = color
            self.layer_controls[layer_name]['color_btn'].setStyleSheet(
                f"background-color: {color.name()}; border: none;")
            self.display_page()

    def display_page(self):
        try:
            if not self.current_pdf or self.current_page < 0 or self.current_page >= len(self.current_pdf):
                return
                
            page = self.current_pdf[self.current_page]
            matrix = fitz.Matrix(self.scale_factor, self.scale_factor)
            matrix.prerotate(self.orientation)
            pix = page.get_pixmap(matrix=matrix)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)
            self.current_pixmap = QPixmap(pixmap)
            
            # Create drawing pixmap
            drawing_pixmap = QPixmap(pixmap)
            painter = QPainter(drawing_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw measurements from each visible layer
            for layer_name, layer in self.layers.items():
                if layer.visible:
                    pen = QPen(layer.color, 2)
                    painter.setPen(pen)
                    
                    for measurement in layer.measurements:
                        if hasattr(measurement, 'points') and len(measurement.points) >= 2:
                            # Draw line
                            painter.drawLine(measurement.points[0], measurement.points[1])
                            
                            # Draw endpoints
                            painter.drawEllipse(measurement.points[0], 5, 5)
                            painter.drawEllipse(measurement.points[1], 5, 5)
                            
                            # Draw measurement text
                            mid_x = (measurement.points[0].x() + measurement.points[1].x()) / 2
                            mid_y = (measurement.points[0].y() + measurement.points[1].y()) / 2
                            
                            # Draw text with background
                            text = f"{measurement.value:.2f} {measurement.unit}"
                            text_rect = painter.fontMetrics().boundingRect(text)
                            text_rect.moveCenter(QPoint(int(mid_x), int(mid_y - 15)))
                            
                            painter.fillRect(text_rect, QColor(255, 255, 255, 200))
                            painter.drawText(text_rect, Qt.AlignCenter, text)
            
            # Draw current measurement points
            if self.measurement_points:
                current_layer = self.layers[self.active_layer]
                painter.setPen(QPen(current_layer.color, 3))
                
                for i, point in enumerate(self.measurement_points):
                    painter.drawEllipse(point, 5, 5)
                    painter.drawLine(point.x() - 10, point.y(), point.x() + 10, point.y())
                    painter.drawLine(point.x(), point.y() - 10, point.x(), point.y() + 10)
                    
                    if i > 0:
                        painter.drawLine(self.measurement_points[i-1], point)
                        
                        if (self.measurement_mode == "calibration" or self.measurement_mode == "distance") and i == 1:
                            pixels = ((point.x() - self.measurement_points[0].x()) ** 2 +
                                    (point.y() - self.measurement_points[0].y()) ** 2) ** 0.5
                            
                            if self.measurement_mode == "calibration":
                                measurement_text = f"{pixels:.1f} pixels"
                            else:
                                feet = pixels / self.scale_calibration
                                measurement_text = f"{feet:.2f} ft"
                            
                            mid_x = (point.x() + self.measurement_points[0].x()) / 2
                            mid_y = (point.y() + self.measurement_points[0].y()) / 2
                            
                            text_rect = painter.fontMetrics().boundingRect(measurement_text)
                            text_rect.moveCenter(QPoint(int(mid_x), int(mid_y - 15)))
                            painter.fillRect(text_rect, QColor(255, 255, 255, 200))
                            painter.drawText(text_rect, Qt.AlignCenter, measurement_text)
            
            painter.end()
            pixmap = drawing_pixmap
            
            self.pdf_label.setPixmap(pixmap)
            self.pdf_label.setMinimumSize(1, 1)
            
            if self.last_mouse_pos and (self.calibration_in_progress or self.measurement_mode):
                self.magnifier.update_magnifier(self.last_mouse_pos, pixmap, force_show=True)
                
        except Exception as e:
            print(f"Error in display_page: {str(e)}")

    def zoom_in(self):
        self.scale_factor *= 1.2
        self.display_page()

    def zoom_out(self):
        self.scale_factor /= 1.2
        self.display_page()

def main():
    app = QApplication(sys.argv)
    ex = QuantityEstimator()
    ex.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
