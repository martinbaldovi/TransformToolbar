# -*- coding: utf-8 -*-
"""
TransformToolbar – Manifold‑style transform toolbar for QGIS 4.0 (Qt6)
"""

import tempfile
import os
import time
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QToolBar, QComboBox, QPushButton, QWidget, QHBoxLayout,
    QSpinBox, QDoubleSpinBox, QLineEdit, QLabel, QFileDialog
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer, QgsUnitTypes,
    QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback,
    QgsMessageLog, Qgis
)
from qgis import processing


class TransformToolbar:
    def __init__(self, iface):
        self.iface = iface
        self.toolbar = None
        self.target_combo = None
        self.operator_combo = None
        self.param_widget = None
        self.apply_btn = None
        self.current_layer = None

    def initGui(self):
        existing = self.iface.mainWindow().findChild(QToolBar, "TransformToolbar")
        if existing:
            existing.deleteLater()

        self.toolbar = QToolBar("Transform Toolbar")
        self.toolbar.setObjectName("TransformToolbar")
        self.toolbar.setWindowTitle("Transform Toolbar")

        self.target_combo = QComboBox()
        self.target_combo.addItems(["All features", "Selected features"])
        self.target_combo.setToolTip("Apply transformation to all or only selected features")
        self.toolbar.addWidget(self.target_combo)

        self.operator_combo = QComboBox()
        self.operator_combo.setToolTip("Choose a transformation operation")
        self.operator_combo.currentTextChanged.connect(self.on_operator_changed)
        self.toolbar.addWidget(self.operator_combo)

        self.param_widget = QWidget()
        param_layout = QHBoxLayout(self.param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar.addWidget(self.param_widget)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setToolTip("Execute the transformation")
        self.apply_btn.clicked.connect(self.run_transformation)
        self.toolbar.addWidget(self.apply_btn)

        self.iface.mainWindow().addToolBar(self.toolbar)
        self.toolbar.setVisible(True)

        self.iface.mapCanvas().currentLayerChanged.connect(self.on_current_layer_changed)
        self.on_current_layer_changed(self.iface.mapCanvas().currentLayer())

    def unload(self):
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None

    def on_current_layer_changed(self, layer):
        self.current_layer = layer
        self.update_operator_list()
        self.on_operator_changed()

    def update_operator_list(self):
        self.operator_combo.clear()
        if not self.current_layer:
            self.operator_combo.addItem("No active layer")
            self.operator_combo.setEnabled(False)
            self.apply_btn.setEnabled(False)
            return

        self.operator_combo.setEnabled(True)
        self.apply_btn.setEnabled(True)

        if isinstance(self.current_layer, QgsVectorLayer):
            ops = [
                ("Buffer", "native:buffer"),
                ("Dissolve", "native:dissolve"),
                ("Clip", "native:clip"),
                ("Intersection", "native:intersection"),
                ("Union", "native:union"),
                ("Difference", "native:difference"),
                ("Simplify", "native:simplifygeometries"),
                ("Centroids", "native:centroids"),
                ("Reproject", "native:reprojectlayer")  # Vector reproject
            ]
        elif isinstance(self.current_layer, QgsRasterLayer):
            ops = [
                ("Clip raster by mask", "gdal:cliprasterbymasklayer"),
                ("Resample", "gdal:warpreproject"),
                ("Reproject", "gdal:warpreproject"),
                ("Translate (format change)", "gdal:translate")
            ]
        else:
            ops = [("Unsupported layer type", "")]
            self.apply_btn.setEnabled(False)

        for display_name, algo_name in ops:
            self.operator_combo.addItem(display_name, algo_name)

    def on_operator_changed(self):
        if not self.current_layer or self.operator_combo.count() == 0:
            return

        operator_text = self.operator_combo.currentText()
        layout = self.param_widget.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        param_widget = self._create_parameter_widget(operator_text)
        if param_widget:
            layout.addWidget(param_widget)
        else:
            layout.addWidget(QLabel("No additional parameters"))

    def _get_vector_unit_string_and_type(self):
        """Return (unit_string, is_degrees) for the current vector layer's CRS."""
        if not isinstance(self.current_layer, QgsVectorLayer):
            return ("units", False)
        crs = self.current_layer.crs()
        if not crs.isValid():
            return ("units", False)
        try:
            unit = crs.mapUnits()
            unit_string = QgsUnitTypes.toString(unit).lower()
            is_degrees = (unit == QgsUnitTypes.DistanceUnit.Degrees)
            return (unit_string, is_degrees)
        except Exception:
            return ("units", False)

    def _get_raster_unit_string_and_type(self):
        """Return (unit_string, is_degrees) for the current raster layer's CRS."""
        if not isinstance(self.current_layer, QgsRasterLayer):
            return ("units", False)
        crs = self.current_layer.crs()
        if not crs.isValid():
            return ("units", False)
        try:
            unit = crs.mapUnits()
            unit_string = QgsUnitTypes.toString(unit).lower()
            is_degrees = (unit == QgsUnitTypes.DistanceUnit.Degrees)
            return (unit_string, is_degrees)
        except Exception:
            return ("units", False)

    def _create_parameter_widget(self, operator_text):
        if operator_text == "Buffer":
            spin = QDoubleSpinBox()
            unit_string, is_degrees = self._get_vector_unit_string_and_type()
            if is_degrees:
                spin.setRange(0.00001, 1e9)
                spin.setDecimals(6)
                spin.setSingleStep(0.0001)
            else:
                spin.setRange(0.0, 1e9)
                spin.setDecimals(3)
                spin.setSingleStep(10.0)
            spin.setValue(100.0)
            spin.setSuffix(f" {unit_string}")
            spin.setToolTip(f"Buffer distance in {unit_string}")
            return spin
        elif operator_text == "Simplify":
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setValue(0.01)
            spin.setSuffix(" tolerance")
            return spin
        elif operator_text in ("Clip", "Intersection", "Union", "Difference"):
            combo = QComboBox()
            all_layers = QgsProject.instance().mapLayers().values()
            vector_layers = [layer for layer in all_layers if isinstance(layer, QgsVectorLayer) and layer != self.current_layer]
            if not vector_layers:
                combo.addItem("No other vector layers available")
                combo.setEnabled(False)
            else:
                for layer in vector_layers:
                    combo.addItem(layer.name(), layer)
            combo.setToolTip(f"Select the overlay vector layer for {operator_text} operation")
            return combo
        elif operator_text.startswith("Clip raster by mask"):
            combo = QComboBox()
            vector_layers = [layer for layer in QgsProject.instance().mapLayers().values()
                             if isinstance(layer, QgsVectorLayer)]
            if not vector_layers:
                combo.addItem("No vector layers available")
                combo.setEnabled(False)
            else:
                for layer in vector_layers:
                    combo.addItem(layer.name(), layer)
            combo.setToolTip("Select the vector mask layer for cookie‑cutter clip")
            return combo
        elif operator_text == "Resample":
            spin = QDoubleSpinBox()
            unit_string, is_degrees = self._get_raster_unit_string_and_type()
            if is_degrees:
                min_val = 0.00001
                decimals = 6
                single_step = 0.0001
            else:
                min_val = 0.0001
                decimals = 3
                single_step = 1.0
            spin.setRange(min_val, 1e9)
            spin.setDecimals(decimals)
            spin.setSingleStep(single_step)
            spin.setValue(10.0)
            spin.setSuffix(f" {unit_string}")
            spin.setToolTip(f"Target cell size in {unit_string} (min: {min_val})")
            return spin
        elif operator_text == "Reproject":
            # Both vector and raster reproject use an EPSG code input
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("EPSG code (e.g., 3857)")
            line_edit.setToolTip("Enter target CRS as EPSG code (e.g., 3857 for Web Mercator, 4326 for WGS84)")
            return line_edit
        elif operator_text == "Translate (format change)":
            combo = QComboBox()
            formats = [
                ("GeoTIFF", "GTiff"),
                ("JPEG", "JPEG"),
                ("PNG", "PNG"),
                ("JPEG2000", "JP2KAK"),
                ("ERDAS Imagine", "HFA"),
                ("ArcInfo ASCII Grid", "AAIGrid"),
                ("NetCDF", "NetCDF"),
                ("GeoPackage", "GPKG")
            ]
            for display_name, gdal_code in formats:
                combo.addItem(display_name, gdal_code)
            combo.setToolTip("Select the output raster format")
            return combo
        else:
            return None

    def run_transformation(self):
        if not self.current_layer:
            self.show_message("No active layer selected.", Qgis.Warning)
            return

        operator_text = self.operator_combo.currentText()
        operator_algo = self.operator_combo.currentData()
        if not operator_algo:
            self.show_message(f"Unknown operator: {operator_text}", Qgis.Critical)
            return

        # Special handling for Translate (format change)
        if operator_text == "Translate (format change)":
            self.run_translate_format_change()
            return

        scope = self.target_combo.currentText()
        use_selection = (scope == "Selected features" and
                         isinstance(self.current_layer, QgsVectorLayer) and
                         self.current_layer.selectedFeatureCount() > 0)

        params = self._build_processing_params(operator_text, operator_algo, use_selection)
        if params is None:
            return

        feedback = QgsProcessingFeedback()
        try:
            result = processing.run(operator_algo, params, feedback=feedback)

            # Handle raster output (explicit file path)
            if operator_algo.startswith("gdal:"):
                output_path = params.get('OUTPUT')
                if output_path and os.path.exists(output_path):
                    if operator_text.startswith("Clip raster by mask"):
                        layer_name = f"Clipped ({self.current_layer.name()})"
                    elif operator_text == "Resample":
                        layer_name = f"Resampled ({self.current_layer.name()})"
                    elif operator_text == "Reproject":
                        layer_name = f"Reprojected ({self.current_layer.name()})"
                    else:
                        layer_name = f"{operator_text} result"
                    raster_layer = QgsRasterLayer(output_path, layer_name)
                    if raster_layer.isValid():
                        QgsProject.instance().addMapLayer(raster_layer)
                        self.iface.mapCanvas().setExtent(raster_layer.extent())
                        self.iface.mapCanvas().refresh()
                        self.show_message(f"Transformation completed. New raster '{layer_name}' added.", Qgis.Success)
                    else:
                        self.show_message(f"Output file exists but could not be loaded as a raster.", Qgis.Warning)
                else:
                    self.show_message(f"Raster transformation completed but output file not found.", Qgis.Warning)
                return

            # Handle vector output (native algorithms)
            if result and 'OUTPUT' in result:
                output = result['OUTPUT']
                if isinstance(output, (QgsVectorLayer, QgsRasterLayer)):
                    # Set consistent name: "<Operation>_output"
                    output.setName(f"{operator_text}_output")
                    QgsProject.instance().addMapLayer(output)
                    self.show_message(f"Transformation '{operator_text}' completed. Layer '{operator_text}_output' added.", Qgis.Success)
                else:
                    # If it's a string (file path) try to load as vector layer
                    if isinstance(output, str) and os.path.exists(output):
                        layer = QgsVectorLayer(output, f"{operator_text}_output", "ogr")
                        if layer.isValid():
                            QgsProject.instance().addMapLayer(layer)
                            self.show_message(f"Transformation '{operator_text}' completed. Layer '{operator_text}_output' added.", Qgis.Success)
                        else:
                            self.show_message(f"Transformation '{operator_text}' completed but output layer could not be loaded.", Qgis.Warning)
                    else:
                        self.show_message(f"Transformation '{operator_text}' completed successfully.", Qgis.Info)
            else:
                self.show_message(f"Transformation '{operator_text}' failed. See log.", Qgis.Warning)

        except Exception as e:
            self.show_message(f"Error: {str(e)}", Qgis.Critical)
            QgsMessageLog.logMessage(str(e), "TransformToolbar", Qgis.Critical)

    def run_translate_format_change(self):
        """Handle 'Translate (format change)' with file save dialog."""
        if not isinstance(self.current_layer, QgsRasterLayer):
            self.show_message("Translate only works on raster layers.", Qgis.Warning)
            return

        combo = self.param_widget.layout().itemAt(0).widget()
        if not isinstance(combo, QComboBox):
            self.show_message("Invalid format selection widget.", Qgis.Critical)
            return
        gdal_format = combo.currentData()
        format_display = combo.currentText()

        extension_map = {
            "GTiff": "tif",
            "JPEG": "jpg",
            "PNG": "png",
            "JP2KAK": "jp2",
            "HFA": "img",
            "AAIGrid": "asc",
            "NetCDF": "nc",
            "GPKG": "gpkg"
        }
        extension = extension_map.get(gdal_format, "tif")

        default_name = f"{self.current_layer.name()}_converted.{extension}"
        output_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Save Translated Raster As",
            default_name,
            f"{format_display} (*.{extension});;All files (*.*)"
        )

        if not output_path:
            return

        if not output_path.lower().endswith(f".{extension}"):
            output_path = f"{output_path}.{extension}"

        params = {
            'INPUT': self.current_layer,
            'OUTPUT': output_path,
            'FORMAT': gdal_format,
            'CREATE_OPTIONS': '',
            'DATA_TYPE': 0,
            'EXTRA': ''
        }

        feedback = QgsProcessingFeedback()
        try:
            result = processing.run("gdal:translate", params, feedback=feedback)
            if result and 'OUTPUT' in result:
                output_path = result['OUTPUT']
                if os.path.exists(output_path):
                    layer_name = f"{self.current_layer.name()} ({format_display})"
                    raster_layer = QgsRasterLayer(output_path, layer_name)
                    if raster_layer.isValid():
                        QgsProject.instance().addMapLayer(raster_layer)
                        self.iface.mapCanvas().setExtent(raster_layer.extent())
                        self.iface.mapCanvas().refresh()
                        self.show_message(f"Translation to {format_display} completed. New layer added.", Qgis.Success)
                    else:
                        self.show_message(f"File saved but could not be loaded: {output_path}", Qgis.Warning)
                else:
                    self.show_message("Translation completed but output file not found.", Qgis.Warning)
            else:
                self.show_message("Translation failed. See log for details.", Qgis.Warning)
        except Exception as e:
            self.show_message(f"Error during translation: {str(e)}", Qgis.Critical)
            QgsMessageLog.logMessage(str(e), "TransformToolbar", Qgis.Critical)

    def _build_processing_params(self, operator_text, operator_algo, use_selection):
        params = {}

        if operator_algo.startswith("native:"):
            if use_selection:
                params['INPUT'] = QgsProcessingFeatureSourceDefinition(
                    self.current_layer.id(), selectedFeaturesOnly=True, featureLimit=-1)
            else:
                params['INPUT'] = self.current_layer
        elif operator_algo.startswith("gdal:"):
            params['INPUT'] = self.current_layer
            if use_selection:
                self.show_message("Selection is ignored for raster layers.", Qgis.Warning)
        else:
            self.show_message(f"Unsupported algorithm type: {operator_algo}", Qgis.Critical)
            return None

        # Output handling
        if operator_algo.startswith("native:"):
            params['OUTPUT'] = 'memory:'
        else:
            # Create a unique temporary GeoTIFF file (Translate is handled separately)
            temp_dir = tempfile.gettempdir()
            temp_file = os.path.join(temp_dir, f"raster_output_{os.getpid()}_{int(time.time())}.tif")
            params['OUTPUT'] = temp_file

        # Operator-specific parameters
        if operator_text == "Buffer":
            spin = self.param_widget.layout().itemAt(0).widget()
            params['DISTANCE'] = spin.value()
            params['SEGMENTS'] = 5
            params['END_CAP_STYLE'] = 0
            params['JOIN_STYLE'] = 0
            params['MITER_LIMIT'] = 2

        elif operator_text == "Dissolve":
            params['FIELD'] = []

        elif operator_text == "Simplify":
            spin = self.param_widget.layout().itemAt(0).widget()
            params['TOLERANCE'] = spin.value()

        elif operator_text in ("Clip", "Intersection", "Union", "Difference"):
            combo = self.param_widget.layout().itemAt(0).widget()
            if not isinstance(combo, QComboBox) or combo.count() == 0 or not combo.currentData():
                self.show_message("No valid overlay layer selected.", Qgis.Warning)
                return None
            params['OVERLAY'] = combo.currentData()

        elif operator_text.startswith("Clip raster by mask"):
            combo = self.param_widget.layout().itemAt(0).widget()
            if not isinstance(combo, QComboBox) or combo.count() == 0 or not combo.currentData():
                self.show_message("No valid vector mask layer selected.", Qgis.Warning)
                return None
            params['MASK'] = combo.currentData()
            params['CROP_TO_CUTLINE'] = True
            params['ALPHA_BAND'] = True
            params['SET_RESOLUTION'] = False

        elif operator_text == "Resample":
            spin = self.param_widget.layout().itemAt(0).widget()
            params['TARGET_RESOLUTION'] = spin.value()
            params['RESAMPLING'] = 0

        elif operator_text == "Reproject":
            # Works for both vector and raster reproject (different algorithms but same parameter name)
            line_edit = self.param_widget.layout().itemAt(0).widget()
            epsg = line_edit.text().strip()
            if not epsg:
                self.show_message("Please enter target EPSG code.", Qgis.Warning)
                return None
            params['TARGET_CRS'] = f'EPSG:{epsg}'
            # For vector reproject, we might also set OPERATION (default is "Convert geometry to target CRS")
            if operator_algo == "native:reprojectlayer":
                params['OPERATION'] = 0  # Convert geometry to target CRS
                params['SMOOTH'] = False  # No smoothing of geometries

        # Translate is handled separately, so not here

        return params

    def show_message(self, text, level=Qgis.Info, duration=3):
        self.iface.messageBar().pushMessage("Transform Toolbar", text, level=level, duration=duration)
