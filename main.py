import sys
import fitz  # PyMuPDF
import math
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, QScrollArea,
                             QInputDialog, QMessageBox, QComboBox, QTreeWidget, 
                             QTreeWidgetItem, QTabWidget, QGroupBox, QFormLayout,
                             QLineEdit, QSpinBox, QDoubleSpinBox, QRadioButton,
                             QButtonGroup, QDialog, QCheckBox, QColorDialog)
from PyQt5.QtCore import Qt, QPointF, QRectF, QPoint
from PyQt5.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont, QIcon, QCursor

class Magnifier(QLabel):
    def __init__(self, parent, zoom_factor=2.5):
        super().__init__(parent)
        self.parent = parent
        self.zoom_factor = zoom_factor
        self.size = 100  # Fixed 100x100 size
        self.setFixedSize(self.size, self.size)
        self.setAlignment(Qt.AlignCenter)
        
        # Semi-transparent background
        self.setStyleSheet("background-color: rgba(255, 255, 255, 180);")
        self.hide()
        
    def update_magnifier(self, pos, source_pixmap, force_show=False):
        """Update magnifier position and content with centered cursor"""
        try:
            if source_pixmap and not source_pixmap.isNull():
                # Calculate source rect size (accounting for zoom)
                source_size = self.size / self.zoom_factor
                
                # Calculate cursor-centered source rectangle
                x = pos.x() - source_size / 2
                y = pos.y() - source_size / 2
                
                # Create source and target rectangles
                source_rect = QRectF(x, y, source_size, source_size)
                target_rect = QRectF(0, 0, self.size, self.size)
                
                # Create magnified image
                magnified = QPixmap(self.size, self.size)
                magnified.fill(Qt.transparent)
                
                painter = QPainter(magnified)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                painter.drawPixmap(target_rect, source_pixmap, source_rect)
                
                # Draw crosshair at center
                painter.setPen(QPen(QColor(0, 0, 0, 180), 1))
                center = QPoint(self.size // 2, self.size // 2)
                painter.drawLine(center.x(), 0, center.x(), self.size)
                painter.drawLine(0, center.y(), self.size, center.y())
                painter.end()
                
                self.setPixmap(magnified)
                
                # Position magnifier relative to cursor
                cursor_pos = self.parent.mapFromGlobal(QCursor.pos())
                magnifier_x = cursor_pos.x() + 20  # Offset from cursor
                magnifier_y = cursor_pos.y() - self.size - 20
                
                # Keep magnifier within parent widget bounds
                parent_rect = self.parent.rect()
                if magnifier_x + self.size > parent_rect.width():
                    magnifier_x = cursor_pos.x() - self.size - 20
                if magnifier_y < 0:
                    magnifier_y = cursor_pos.y() + 20
                
                self.move(magnifier_x, magnifier_y)
                
                if force_show and not self.isVisible():
                    self.show()
                    
        except Exception as e:
            print(f"Error updating magnifier: {str(e)}")
            
    def cleanup(self):
        """Clean up resources"""
        if self.pixmap():
            self.setPixmap(QPixmap())
        self.hide()

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
        self.layers = {
            'Calibration': DrawingLayer('Calibration', QColor(0, 150, 0)),  # Green
            'Distance': DrawingLayer('Distance', QColor(0, 0, 255)),  # Blue
            'Area': DrawingLayer('Area', QColor(255, 0, 0))  # Red
        }
        self.active_layer = 'Distance'  # Default active layer
        
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
        self.show_magnifier = True  # Always show magnifier
        self.last_mouse_pos = None
        
        self.initUI()
        self.setWindowTitle('Quantity Estimator')
        self.setGeometry(100, 100, 1400, 800)
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)

    def mouseMoveEvent(self, event):
        if self.current_pixmap and self.magnifier:
            pdf_pos = self.pdf_label.mapFromGlobal(event.globalPos())
            if self.pdf_label.rect().contains(pdf_pos):
                self.magnifier.update_magnifier(pdf_pos, self.current_pixmap, True)
            else:
                self.magnifier.hide()
        super().mouseMoveEvent(event)

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

    def add_measurement_to_list(self, measurement_type, value, unit, description=None):
        """Add a measurement to the tree widget and layer"""
        try:
            if not description:
                description = f"{measurement_type} {len(self.measurements) + 1}"
            
            measurement = MeasurementItem(measurement_type, value, unit, description)
            measurement.points = self.measurement_points.copy()
            
            layer_name = measurement_type if measurement_type in self.layers else 'Distance'
            self.layers[layer_name].measurements.append(measurement)
            self.measurements.append(measurement)
            
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
        file_name, _ = QFileDialog.getOpenFileName(self, "Open PDF File", "", "PDF Files (*.pdf)")
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
        """Start calibration process with scale handling"""
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
            
            # Update UI to show calibration mode
            self.pdf_label.setCursor(Qt.CrossCursor)
            self.measurement_type.setCurrentText('None')
            
            QMessageBox.information(self, "Calibration", 
                "Click two points to set the scale reference distance")
                
        except Exception as e:
            print(f"Error starting calibration: {str(e)}")
            self.cleanup_calibration()
            
    def handle_measurement(self, event_pos):
        if not self.measurement_mode:
            return
        
        measurement_handlers = {
            'distance': self.handle_distance_measurement,
            'area': self.handle_area_measurement,
            'count': self.handle_count_measurement,
            'calibration': self.handle_calibration_measurement
        }
        if self.measurement_mode in measurement_handlers:
            measurement_handlers[self.measurement_mode](event_pos)

    def draw_measurements(self, painter):
        """Draw all measurements with optimized layer handling"""
        try:
            visible_layers = {name: layer for name, layer in self.layers.items() 
                            if layer.visible}
            
            for layer_name, layer in visible_layers.items():
                pen = QPen(layer.color, 2)
                painter.setPen(pen)
                
                if layer_name == 'Calibration' and self.calibration_in_progress:
                    if len(self.measurement_points) >= 2:
                        painter.drawLine(self.measurement_points[0], self.measurement_points[1])
                        
                elif layer_name == 'Distance' and self.measurement_mode == 'distance':
                    if len(self.measurement_points) >= 2:
                        painter.drawLine(self.measurement_points[0], self.measurement_points[1])
                        
                elif layer_name == 'Area' and self.measurement_mode == 'area':
                    self.draw_area_polygon(painter)
                    
        except Exception as e:
            print(f"Error in draw_measurements: {str(e)}")
            
    def draw_area_polygon(self, painter):
        """Draw area polygon with optimized point handling"""
        if len(self.measurement_points) < 2:
            return
            
        # Draw existing lines
        points = self.measurement_points
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
            
        # Draw current line and closing lines
        if self.drawing and self.current_measurement:
            painter.drawLine(points[-1], self.current_measurement)
            if len(points) >= 3:
                painter.drawLine(self.current_measurement, points[0])
        elif len(points) >= 3:
            painter.drawLine(points[-1], points[0])

    def on_mouse_press(self, event):
        if event.button() == Qt.LeftButton:
            self.handle_measurement(event.pos())

    def on_mouse_move(self, event):
        try:
            if not self.pdf_label.pixmap() or self.pdf_label.pixmap().isNull():
                return
            self.last_mouse_pos = event.pos()
            if self.show_magnifier and self.magnifier and self.current_pixmap:
                viewport_pos = self.pdf_label.mapFromGlobal(QCursor.pos())
                self.magnifier.update_magnifier(viewport_pos, self.current_pixmap, force_show=True)
            if self.drawing and self.measurement_mode == "area":
                self.current_measurement = event.pos()
                self.display_page()
        except Exception as e:
            print(f"Error in mouse move: {str(e)}")

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
                distance, ok = QInputDialog.getDouble(self, "Enter Distance",
                    "Enter the actual distance (in feet):", 1, 0, 1000, 2)
                if ok:
                    self.scale_calibration = pixels / distance
                    QMessageBox.information(self, "Calibration Complete", 
                        f"Scale set to {distance:.2f} feet per {pixels:.2f} pixels")
                else:
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
        if event.key() == Qt.Key_Escape:
            self.cleanup_calibration()

    def change_measurement_mode(self, mode):
        """Change the current measurement mode and update UI"""
        # Reset current measurement state
        self.measurement_points = []
        self.current_measurement = None
        self.drawing = False
        self.show_magnifier = True  # Always keep magnifier active
        
        # Set measurement mode and active layer
        if mode == 'None':
            self.measurement_mode = None
            self.active_layer = None
        else:
            self.measurement_mode = mode.lower()
            self.active_layer = mode
        
        # Update cursor based on measurement mode
        if self.measurement_mode in ['distance', 'area', 'count']:
            self.pdf_label.setCursor(Qt.CrossCursor)
        else:
            self.pdf_label.setCursor(Qt.ArrowCursor)
        
        self.display_page()

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
        """Toggle visibility of a measurement layer"""
        if layer_name in self.layers:
            self.layers[layer_name].visible = bool(state)
            self.display_page()

    def change_layer_color(self, layer_name):
        """Change the color of a measurement layer"""
        if layer_name in self.layers:
            color = QColorDialog.getColor(self.layers[layer_name].color)
            if color.isValid():
                self.layers[layer_name].color = color
                btn = self.layer_controls[layer_name]['color_button']
                btn.setStyleSheet(f"background-color: {color.name()}; border: none;")
                self.display_page()

    def handle_distance_measurement(self, pos):
        """Handle distance measurement logic"""
        self.measurement_points.append(pos)
        if len(self.measurement_points) == 2:
            self.calculate_distance()
            self.measurement_points = []
            self.display_page()

    def handle_area_measurement(self, pos):
        """Handle area measurement logic"""
        self.measurement_points.append(pos)
        self.drawing = True
        if len(self.measurement_points) >= 3:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.ControlModifier:
                self.calculate_area()
                self.drawing = False
                self.measurement_points = []
        self.display_page()

    def handle_count_measurement(self, pos):
        """Handle count measurement logic"""
        description = self.description_input.text() or f"Point {len(self.measurements) + 1}"
        self.add_measurement_to_list("Count", 1, "point", description)
        self.display_page()

    def handle_calibration_measurement(self, pos):
        """Handle calibration measurement logic"""
        self.measurement_points.append(pos)
        if len(self.measurement_points) == 2:
            self.display_page()
            self.prompt_for_distance()
            self.measurement_points = []
            self.calibration_in_progress = False

    def prompt_for_distance(self):
        """Prompt user for actual distance during calibration"""
        try:
            p1, p2 = self.measurement_points
            pixels = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
            
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

    def calculate_area(self):
        """Calculate polygon area with optimized loop"""
        if len(self.measurement_points) < 3:
            return
            
        points = self.measurement_points
        n = len(points)
        area = sum(points[i].x() * points[(i + 1) % n].y() - 
                  points[(i + 1) % n].x() * points[i].y() 
                  for i in range(n))
        area = abs(area) / 2
        
        if self.scale_calibration:
            square_feet = area / (self.scale_calibration ** 2)
            description = self.description_input.text()
            self.add_measurement_to_list("Area", square_feet, "sq.ft", description)
        
        self.drawing = False
        self.measurement_points = []
        self.current_measurement = None
        self.display_page()
        
    def calculate_distance(self):
        """Calculate distance with vector math"""
        if len(self.measurement_points) != 2:
            return
            
        p1, p2 = self.measurement_points
        pixels = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
        
        if self.scale_calibration:
            feet = pixels / self.scale_calibration
            description = self.description_input.text()
            self.add_measurement_to_list("Distance", feet, "feet", description)
            
        self.measurement_points = []
        self.display_page()
        
    def display_page(self):
        """Display PDF page with centered zoom"""
        if not self.current_pdf:
            return
            
        try:
            # Get the current page
            page = self.current_pdf[self.current_page]
            
            # Create transformation matrix with scale and rotation
            matrix = fitz.Matrix(self.scale_factor, self.scale_factor)
            if self.orientation != 0:
                matrix.preRotate(self.orientation)
            
            # Render the page
            pix = page.get_pixmap(matrix=matrix)
            fmt = QImage.Format_RGBA8888 if pix.alpha else QImage.Format_RGB888
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            self.current_pixmap = QPixmap.fromImage(img)
            
            # Draw measurements
            painter = QPainter(self.current_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            self.draw_measurements(painter)
            painter.end()
            
            # Update PDF label
            self.pdf_label.setPixmap(self.current_pixmap)
            
            # Center the page in the scroll area
            self.center_page_in_scroll_area()
            
        except Exception as e:
            print(f"Error in display_page: {str(e)}")
            
    def center_page_in_scroll_area(self):
        """Center the page in scroll area after zoom"""
        if not self.current_pixmap:
            return
            
        # Get the scroll area viewport size
        viewport_size = self.scroll_area.viewport().size()
        
        # Calculate content margins to center the page
        margin_x = max(0, (viewport_size.width() - self.current_pixmap.width()) // 2)
        margin_y = max(0, (viewport_size.height() - self.current_pixmap.height()) // 2)
        
        # Set margins to center content
        self.pdf_label.setContentsMargins(margin_x, margin_y, margin_x, margin_y)
        
    def zoom_in(self):
        """Zoom in with proportional calibration update"""
        try:
            ZOOM_FACTOR = 1.2
            if self.current_pixmap:
                # Save current center
                scrollbar_x = self.scroll_area.horizontalScrollBar()
                scrollbar_y = self.scroll_area.verticalScrollBar()
                center_x = scrollbar_x.value() + self.scroll_area.viewport().width() / 2
                center_y = scrollbar_y.value() + self.scroll_area.viewport().height() / 2
                rel_x = center_x / self.current_pixmap.width()
                rel_y = center_y / self.current_pixmap.height()
                
                # Update scale and calibration
                old_scale = self.scale_factor
                self.scale_factor = min(5.0, self.scale_factor * ZOOM_FACTOR)
                
                # Update calibration value proportionally
                if hasattr(self, 'scale_value') and self.scale_calibration:
                    current_cal = self.scale_value.value()
                    new_cal = current_cal * ZOOM_FACTOR
                    self.scale_value.setValue(new_cal)
                    self.scale_calibration *= ZOOM_FACTOR
                
                # Update display
                self.display_page()
                
                # Restore center
                new_x = rel_x * self.current_pixmap.width() - self.scroll_area.viewport().width() / 2
                new_y = rel_y * self.current_pixmap.height() - self.scroll_area.viewport().height() / 2
                scrollbar_x.setValue(int(new_x))
                scrollbar_y.setValue(int(new_y))
                
                # Update magnifier
                if self.magnifier:
                    self.magnifier.zoom_factor = min(5.0, 2.5 * self.scale_factor)
                    
        except Exception as e:
            print(f"Zoom in error: {str(e)}")

    def zoom_out(self):
        """Zoom out with proportional calibration update"""
        try:
            ZOOM_FACTOR = 1/1.2
            if self.current_pixmap:
                # Save current center
                scrollbar_x = self.scroll_area.horizontalScrollBar()
                scrollbar_y = self.scroll_area.verticalScrollBar()
                center_x = scrollbar_x.value() + self.scroll_area.viewport().width() / 2
                center_y = scrollbar_y.value() + self.scroll_area.viewport().height() / 2
                rel_x = center_x / self.current_pixmap.width()
                rel_y = center_y / self.current_pixmap.height()
                
                # Update scale and calibration
                old_scale = self.scale_factor
                self.scale_factor = max(0.2, self.scale_factor * ZOOM_FACTOR)
                
                # Update calibration value proportionally
                if hasattr(self, 'scale_value') and self.scale_calibration:
                    current_cal = self.scale_value.value()
                    new_cal = current_cal * ZOOM_FACTOR
                    self.scale_value.setValue(new_cal)
                    self.scale_calibration *= ZOOM_FACTOR
                
                # Update display
                self.display_page()
                
                # Restore center
                new_x = rel_x * self.current_pixmap.width() - self.scroll_area.viewport().width() / 2
                new_y = rel_y * self.current_pixmap.height() - self.scroll_area.viewport().height() / 2
                scrollbar_x.setValue(int(new_x))
                scrollbar_y.setValue(int(new_y))
                
                # Update magnifier
                if self.magnifier:
                    self.magnifier.zoom_factor = max(1.5, 2.5 * self.scale_factor)
                    
        except Exception as e:
            print(f"Zoom out error: {str(e)}")

    def calculate_calibration(self, pixels, distance):
        """Calculate and apply calibration scale"""
        try:
            if pixels <= 0 or distance <= 0:
                raise ValueError("Invalid calibration values")
                
            # Calculate new scale calibration based on current zoom level
            new_calibration = (pixels * self.scale_factor) / distance
            
            if self.scale_calibration and self.scale_calibration > 0:
                # Adjust existing measurements for new calibration
                calibration_ratio = new_calibration / self.scale_calibration
                for layer in self.layers.values():
                    for measurement in layer.measurements:
                        if hasattr(measurement, 'value'):
                            measurement.value /= calibration_ratio
                            
            self.scale_calibration = new_calibration
            self.scale_value.setValue(distance)
            
            # Update display
            self.display_page()
            
        except Exception as e:
            print(f"Error in calibration calculation: {str(e)}")
            self.scale_calibration = 1.0

    def adjust_measurements_for_zoom(self, old_scale, new_scale):
        """Adjust measurements when zooming"""
        try:
            scale_ratio = new_scale / old_scale
            
            # Adjust current measurement points
            if self.measurement_points:
                for i, point in enumerate(self.measurement_points):
                    new_x = point.x() * scale_ratio
                    new_y = point.y() * scale_ratio
                    self.measurement_points[i] = QPointF(new_x, new_y)
            
            # Adjust all stored measurements
            for layer in self.layers.values():
                for measurement in layer.measurements:
                    if hasattr(measurement, 'points') and measurement.points:
                        # Scale the points
                        for i, point in enumerate(measurement.points):
                            new_x = point.x() * scale_ratio
                            new_y = point.y() * scale_ratio
                            measurement.points[i] = QPointF(new_x, new_y)
                        
                        # Update measurement value based on new points
                        if measurement.type == "Distance" and len(measurement.points) == 2:
                            p1, p2 = measurement.points
                            pixels = ((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) ** 0.5
                            if self.scale_calibration:
                                measurement.value = pixels / self.scale_calibration
                                
                        elif measurement.type == "Area" and len(measurement.points) >= 3:
                            area = 0
                            points = measurement.points
                            for i in range(len(points)):
                                j = (i + 1) % len(points)
                                area += points[i].x() * points[j].y()
                                area -= points[j].x() * points[i].y()
                            area = abs(area) / 2
                            if self.scale_calibration:
                                measurement.value = area / (self.scale_calibration ** 2)
                    
        except Exception as e:
            print(f"Error adjusting measurements for zoom: {str(e)}")

    def update_calibration_scale(self, new_scale):
        """Update calibration and adjust all measurements"""
        try:
            if new_scale <= 0:
                return
                
            if self.scale_calibration and self.scale_calibration > 0:
                # Calculate ratio between old and new calibration
                scale_ratio = new_scale / self.scale_calibration
                
                # Update all measurements with new scale
                for layer in self.layers.values():
                    for measurement in layer.measurements:
                        if measurement.type == "Distance":
                            measurement.value *= scale_ratio
                        elif measurement.type == "Area":
                            measurement.value *= (scale_ratio ** 2)
            
            self.scale_calibration = new_scale
            self.display_page()
            
        except Exception as e:
            print(f"Error updating calibration scale: {str(e)}")

    def initUI(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        sidebar = QWidget()
        sidebar.setMaximumWidth(300)
        sidebar.setMinimumWidth(250)
        sidebar_layout = QVBoxLayout(sidebar)

        project_group = QGroupBox("Project Information")
        project_layout = QFormLayout()
        self.project_name = QLineEdit()
        self.project_number = QLineEdit()
        project_layout.addRow("Project Name:", self.project_name)
        project_layout.addRow("Project Number:", self.project_number)
        project_group.setLayout(project_layout)
        sidebar_layout.addWidget(project_group)

        tools_group = QGroupBox("Measurement Tools")
        tools_layout = QVBoxLayout()

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

        measurements_group = QGroupBox("Measurements")
        measurements_layout = QVBoxLayout()
        self.measurements_tree = QTreeWidget()
        self.measurements_tree.setHeaderLabels(['Type', 'Value', 'Description'])
        self.measurements_tree.setColumnCount(3)
        measurements_layout.addWidget(self.measurements_tree)
        measurements_group.setLayout(measurements_layout)
        sidebar_layout.addWidget(measurements_group)

        layer_group = QGroupBox("Layers")
        layer_layout = QVBoxLayout()
        
        self.layer_controls = {}
        for layer_name in self.layers:
            layer_widget = QWidget()
            layer_h_layout = QHBoxLayout()
            layer_widget.setLayout(layer_h_layout)
            visibility_cb = QCheckBox()
            visibility_cb.setChecked(True)
            visibility_cb.stateChanged.connect(lambda state, name=layer_name: self.toggle_layer_visibility(name, state))
            color_btn = QPushButton()
            color_btn.setFixedSize(20, 20)
            color_btn.setStyleSheet(f"background-color: {self.layers[layer_name].color.name()}; border: none;")
            color_btn.clicked.connect(lambda checked, name=layer_name: self.change_layer_color(name))
            name_label = QLabel(layer_name)
            layer_h_layout.addWidget(visibility_cb)
            layer_h_layout.addWidget(color_btn)
            layer_h_layout.addWidget(name_label)
            layer_h_layout.addStretch()
            self.layer_controls[layer_name] = {
                'widget': layer_widget,
                'checkbox': visibility_cb,
                'color_button': color_btn
            }
            layer_layout.addWidget(layer_widget)
        
        layer_group.setLayout(layer_layout)
        sidebar_layout.addWidget(layer_group)

        main_layout.addWidget(sidebar)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

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

def main():
    app = QApplication(sys.argv)
    ex = QuantityEstimator()
    ex.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
