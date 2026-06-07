# -*- coding: utf-8 -*-
"""
TransformToolbar – Manifold‑style transform toolbar for QGIS 4.0 (Qt6)
"""

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QToolBar, QComboBox, QPushButton, QWidget, QHBoxLayout,
    QSpinBox, QDoubleSpinBox, QLineEdit, QLabel
)
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsRasterLayer,
    QgsProcessingFeatureSourceDefinition, QgsProcessingFeedback,
    QgsMessageLog, Qgis
)
from qgis import processing


class TransformToolbar:
    """Main plugin class that creates and manages the Transform Toolbar."""

    def __init__(self, iface):
        """Initialize the plugin with the QGIS interface."""
        self.iface = iface
        self.toolbar = None
        self.target_combo = None
        self.operator_combo = None
        self.param_widget = None
        self.apply_btn = None
        self.current_layer = None

    def initGui(self):
        """Create the toolbar and its widgets when the plugin is loaded."""
        # Remove any existing instance of the toolbar
        existing = self.iface.mainWindow().findChild(QToolBar, "TransformToolbar")
        if existing:
            existing.deleteLater()

        # Create the main toolbar
        self.toolbar = QToolBar("Transform Toolbar")
        self.toolbar.setObjectName("TransformToolbar")
        self.toolbar.setWindowTitle("Transform Toolbar")

        # --- Target box (scope) ---
        self.target_combo = QComboBox()
        self.target_combo.addItems(["All features", "Selected features"])
        self.target_combo.setToolTip("Apply transformation to all or only selected features")
        self.toolbar.addWidget(self.target_combo)

        # --- Operator box (transformation) ---
        self.operator_combo = QComboBox()
        self.operator_combo.setToolTip("Choose a transformation operation")
        self.operator_combo.currentTextChanged.connect(self.on_operator_changed)
        self.toolbar.addWidget(self.operator_combo)

        # --- Parameter box (dynamic) ---
        self.param_widget = QWidget()
        param_layout = QHBoxLayout(self.param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar.addWidget(self.param_widget)

        # --- Apply button ---
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setToolTip("Execute the transformation")
        self.apply_btn.clicked.connect(self.run_transformation)
        self.toolbar.addWidget(self.apply_btn)

        # Add toolbar to QGIS main window
        self.iface.mainWindow().addToolBar(self.toolbar)
        self.toolbar.setVisible(True)

        # Connect signals to update the operator list when the active layer changes
        self.iface.mapCanvas().currentLayerChanged.connect(self.on_current_layer_changed)
        # Initial update
        self.on_current_layer_changed(self.iface.mapCanvas().currentLayer())

    def unload(self):
        """Clean up when the plugin is unloaded."""
        if self.toolbar:
            self.toolbar.deleteLater()
            self.toolbar = None

    def on_current_layer_changed(self, layer):
        """Update the operator list when a new layer becomes active."""
        self.current_layer = layer
        self.update_operator_list()
        self.on_operator_changed()  # refresh parameter widget

    def update_operator_list(self):
        """Populate the operator combo box based on the current layer type."""
        self.operator_combo.clear()
        if not self.current_layer:
            self.operator_combo.addItem("No active layer")
            self.operator_combo.setEnabled(False)
            self.apply_btn.setEnabled(False)
            return

        self.operator_combo.setEnabled(True)
        self.apply_btn.setEnabled(True)

        if isinstance(self.current_layer, QgsVectorLayer):
            # Vector operators (matching common Processing algorithms)
            ops = [
                ("Buffer", "native:buffer"),
                ("Dissolve", "native:dissolve"),
                ("Clip", "native:clip"),
                ("Intersection", "native:intersection"),
                ("Union", "native:union"),
                ("Difference", "native:difference"),
                ("Simplify", "native:simplifygeometries"),
                ("Centroids", "native:centroids")
            ]
        elif isinstance(self.current_layer, QgsRasterLayer):
            # Raster operators
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
        """Rebuild the parameter widget when the operator changes."""
        if not self.current_layer or self.operator_combo.count() == 0:
            return

        operator_text = self.operator_combo.currentText()
        layout = self.param_widget.layout()
        # Clear existing widget
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # Create a new parameter widget based on the selected operator
        param_widget = self._create_parameter_widget(operator_text)
        if param_widget:
            layout.addWidget(param_widget)
        else:
            # Add a placeholder label if no parameters needed
            label = QLabel("No additional parameters")
            layout.addWidget(label)

    def _create_parameter_widget(self, operator_text):
        """Return a QWidget suitable for the given operator's parameters."""
        if operator_text == "Buffer":
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1e9)
            spin.setValue(100.0)
            spin.setSuffix(" m")
            spin.setToolTip("Buffer distance in map units")
            return spin
        elif operator_text == "Simplify":
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setValue(0.01)
            spin.setSuffix(" tolerance")
            spin.setToolTip("Simplification tolerance (0 = no change, 1 = max)")
            return spin
        elif operator_text in ("Clip", "Intersection", "Union", "Difference"):
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("Layer name or ID (e.g., 'buildings')")
            line_edit.setToolTip("Enter the name of the overlay layer")
            return line_edit
        elif operator_text.startswith("Clip raster by mask"):
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("Mask layer name")
            line_edit.setToolTip("Vector layer used as mask")
            return line_edit
        elif operator_text == "Resample":
            spin = QSpinBox()
            spin.setRange(1, 1000)
            spin.setValue(10)
            spin.setSuffix(" m")
            spin.setToolTip("Target cell size (meters)")
            return spin
        elif operator_text == "Reproject":
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("EPSG code (e.g., 3857)")
            line_edit.setToolTip("Target CRS (EPSG code)")
            return line_edit
        elif operator_text == "Translate (format change)":
            line_edit = QLineEdit()
            line_edit.setPlaceholderText("Output format (e.g., GTiff, PNG)")
            line_edit.setToolTip("GDAL driver short name")
            return line_edit
        else:
            return None

    def run_transformation(self):
        """Execute the selected transformation using QGIS Processing."""
        if not self.current_layer:
            self.show_message("No active layer selected.", Qgis.Warning)
            return

        operator_text = self.operator_combo.currentText()
        operator_algo = self.operator_combo.currentData()
        if not operator_algo:
            self.show_message(f"Unknown operator: {operator_text}", Qgis.Critical)
            return

        # Determine scope (all or selected features)
        scope = self.target_combo.currentText()
        use_selection = (scope == "Selected features" and
                         isinstance(self.current_layer, QgsVectorLayer) and
                         self.current_layer.selectedFeatureCount() > 0)

        # Build Processing parameters
        params = self._build_processing_params(operator_text, operator_algo, use_selection)
        if params is None:
            return  # error already shown

        # Run the algorithm
        feedback = QgsProcessingFeedback()
        try:
            result = processing.run(operator_algo, params, feedback=feedback)
            if result and 'OUTPUT' in result:
                output_layer = result['OUTPUT']
                # Add output layer to the project if it's a new layer
                if isinstance(output_layer, (QgsVectorLayer, QgsRasterLayer)):
                    QgsProject.instance().addMapLayer(output_layer)
                    self.show_message(
                        f"Transformation '{operator_text}' completed. New layer added.",
                        Qgis.Success
                    )
                else:
                    self.show_message(
                        f"Transformation '{operator_text}' completed successfully.",
                        Qgis.Info
                    )
            else:
                self.show_message(f"Transformation '{operator_text}' failed. See log for details.", Qgis.Warning)
        except Exception as e:
            self.show_message(f"Error: {str(e)}", Qgis.Critical)
            QgsMessageLog.logMessage(str(e), "TransformToolbar", Qgis.Critical)

    def _build_processing_params(self, operator_text, operator_algo, use_selection):
        """Build the parameter dictionary for the selected algorithm."""
        params = {}

        # Common input handling
        if operator_algo.startswith("native:"):
            # Vector algorithms
            if use_selection:
                params['INPUT'] = QgsProcessingFeatureSourceDefinition(
                    self.current_layer.id(),
                    selectedFeaturesOnly=True,
                    featureLimit=-1
                )
            else:
                params['INPUT'] = self.current_layer
        elif operator_algo.startswith("gdal:"):
            # Raster algorithms
            params['INPUT'] = self.current_layer
            if use_selection:
                self.show_message("Selection is ignored for raster layers.", Qgis.Warning)
        else:
            self.show_message(f"Unsupported algorithm type: {operator_algo}", Qgis.Critical)
            return None

        # Set output to temporary layer (memory for vectors, temp file for rasters)
        if operator_algo.startswith("native:"):
            params['OUTPUT'] = 'memory:'
        else:
            params['OUTPUT'] = 'TEMPORARY_OUTPUT'

        # Operator-specific parameters
        if operator_text == "Buffer":
            spin = self.param_widget.layout().itemAt(0).widget()
            params['DISTANCE'] = spin.value()
            params['SEGMENTS'] = 5
            params['END_CAP_STYLE'] = 0
            params['JOIN_STYLE'] = 0
            params['MITER_LIMIT'] = 2

        elif operator_text == "Dissolve":
            params['FIELD'] = []  # dissolve all features

        elif operator_text == "Simplify":
            spin = self.param_widget.layout().itemAt(0).widget()
            params['TOLERANCE'] = spin.value()

        elif operator_text in ("Clip", "Intersection", "Union", "Difference"):
            line_edit = self.param_widget.layout().itemAt(0).widget()
            overlay_name = line_edit.text().strip()
            if not overlay_name:
                self.show_message("Please enter the name of the overlay layer.", Qgis.Warning)
                return None
            overlay_layer = QgsProject.instance().mapLayersByName(overlay_name)
            if not overlay_layer:
                self.show_message(f"Overlay layer '{overlay_name}' not found.", Qgis.Warning)
                return None
            params['OVERLAY'] = overlay_layer[0]

        elif operator_text.startswith("Clip raster by mask"):
            line_edit = self.param_widget.layout().itemAt(0).widget()
            mask_name = line_edit.text().strip()
            if not mask_name:
                self.show_message("Please enter the mask layer name.", Qgis.Warning)
                return None
            mask_layer = QgsProject.instance().mapLayersByName(mask_name)
            if not mask_layer:
                self.show_message(f"Mask layer '{mask_name}' not found.", Qgis.Warning)
                return None
            params['MASK'] = mask_layer[0]

        elif operator_text == "Resample":
            spin = self.param_widget.layout().itemAt(0).widget()
            params['TARGET_RESOLUTION'] = spin.value()
            params['RESAMPLING'] = 0  # nearest neighbour

        elif operator_text == "Reproject":
            line_edit = self.param_widget.layout().itemAt(0).widget()
            epsg = line_edit.text().strip()
            if not epsg:
                self.show_message("Please enter target EPSG code.", Qgis.Warning)
                return None
            params['TARGET_CRS'] = f'EPSG:{epsg}'

        elif operator_text == "Translate (format change)":
            line_edit = self.param_widget.layout().itemAt(0).widget()
            fmt = line_edit.text().strip()
            if not fmt:
                self.show_message("Please enter output format (e.g., GTiff).", Qgis.Warning)
                return None
            params['FORMAT'] = fmt

        return params

    def show_message(self, text, level=Qgis.Info, duration=3):
        """Display a message in the QGIS message bar."""
        self.iface.messageBar().pushMessage("Transform Toolbar", text, level=level, duration=duration)
