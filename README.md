# LFA-Analyzer: Interactive Computer Vision and Densitometry Suite for Lateral Flow Assay Quantification

[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![GUI-Tkinter](https://img.shields.io/badge/GUI-Tkinter-blue.svg?style=flat-square)](https://docs.python.org/3/library/tkinter.html)
[![Densitometry-Engine](https://img.shields.io/badge/Engine-NumPy%20%7C%20Pillow%20%7C%20Matplotlib-orange.svg?style=flat-square)](https://numpy.org/)
[![Pre--processing-Fiji%20Homography](https://img.shields.io/badge/Pre--processing-Fiji%20%2F%20ImageJ-blueviolet.svg?style=flat-square)](https://fiji.sc/)
[![Academic-Research](https://img.shields.io/badge/Research-Bioanalytical%20Diagnostics-success.svg?style=flat-square)]()

---

## 1. Abstract and Analytical Overview

Lateral Flow Assays (LFAs) represent one of the most widely deployed point-of-care (PoC) diagnostic platforms across clinical, veterinary, food safety, and environmental domains. Although traditionally deployed as qualitative binary (yes/no) readout devices, there is an increasing demand for objective, semi-quantitative, and fully quantitative diagnostic evaluations. Variable ambient illumination, phone camera perspective distortions, strip misalignment inside cassette windows, and non-uniform nitrocellulose background coloration frequently compromise photometric reproducibility.

**LFA-Analyzer** is an open-source, specialized computer vision and analytical densitometry framework engineered to transform qualitative LFA strips into rigorous, background-subtracted optical density measurements. The analytical pipeline couples:
1. **Planar Homography Rectification (`Four_Point_Crop.py`)**: An ImageJ/Fiji Jython plugin utilizing 2D projective transformation matrices to correct perspective distortion, tilt, and optical skew, isolating the active test membrane into a standardized, rectangular image matrix.
2. **Interactive Analytical Densitometry Engine (`strip_analyzer.py`)**: A native Python desktop application featuring float64 multi-channel array deconvolution, decoupled display-enhancement visualization, user-calibrated multi-region of interest (ROI) profiling, robust central-tendency statistics (mean vs. median), and automated batch quantification with CSV telemetry export.

<p align="center">
  <img src="demo.png" alt="LFA-Analyzer Graphical User Interface" width="92%" />
</p>
<p align="center"><em>Figure 1: LFA-Analyzer graphical desktop interface showing rectified strip alignment, draggable multi-band region of interest (ROI) overlays (Control: Blue, Test 2: Green, Test 1: Red, Background: Orange), dynamic distance controls, and real-time contrast visualization.</em></p>

---

## 2. Key Capabilities and Technical Innovations

* **Full-Precision Floating-Point Densitometry**: Native support for 8-bit RGB/PNG/JPEG and high-dynamic-range 16-bit grayscale TIFF formats (`I`, `I;16`, `I;16B`, `I;16L`, `F`). Raw pixel intensities are loaded directly into `float64` NumPy arrays without down-sampling or destructive quantization.
* **Separation of Visualization from Quantification**: All contrast enhancement filters (local background illumination flattening via cumulative-sum 2D box blur and ImageJ-style percentile saturation stretching) operate exclusively on display-only 8-bit viewports. Quantified optical metrics are calculated strictly against the unmanipulated raw signal array.
* **Spectral Channel Deconvolution**: Supports selective single-channel analysis across Red, Green, Blue, or Luminance channels. For colorimetric colloidal gold (absorbing strongly in the green channel) or latex nanoparticle conjugates, targeting the complementary wavelength band markedly enhances signal-to-noise ratios (SNR).
* **Synchronized Draggable ROI Geometry**: Features an intuitive spatial alignment system where translating the reference Control band ($Y_{\text{Control}}$) maintains calibrated relative offsets for Test Line 2 ($\Delta Y_{T2}$), Test Line 1 ($\Delta Y_{T1}$), and Local Background ($\Delta Y_{\text{BG}}$), accounting for manufacturing tolerances across strip batches.
* **Outlier-Resistant Central Tendency**: Supports real-time switching between mean intensity and median intensity over the integration slit, neutralizing the impact of dust particles, nitrocellulose membrane defects, or edge shadowing.
* **Automated Batch Processing & Analytics**: Enables one-click evaluation across multi-image directories. Generates synchronized Matplotlib diagnostic bar plots for net optical density and normalized Test-to-Control ($T/C$) ratios alongside structured CSV telemetry output.

---

## 3. Mathematical and Theoretical Formulation

### 3.1 Planar Homography Perspective Transformation

During strip image capture under unconstrained conditions, the camera optical axis is rarely perpendicular to the strip plane, introducing a 2D projective distortion. The relationship between physical strip coordinates $\mathbf{x} = [x, y, 1]^T$ and observed sensor coordinates $\mathbf{x}' = [x', y', 1]^T$ is governed by a planar homography matrix $\mathbf{H} \in \mathbb{R}^{3 \times 3}$:

$$\begin{bmatrix} x' \\ y' \\ 1 \end{bmatrix} \sim \mathbf{H} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix} = \begin{bmatrix} h_{11} & h_{12} & h_{13} \\ h_{21} & h_{22} & h_{23} \\ h_{31} & h_{32} & h_{33} \end{bmatrix} \begin{bmatrix} x \\ y \\ 1 \end{bmatrix}$$

Using the ImageJ plugin `Four_Point_Crop.py`, the user designates four coplanar corner vertices:
* $P_1 = (x_1, y_1)$ [Top-Left]
* $P_2 = (x_2, y_2)$ [Top-Right]
* $P_3 = (x_3, y_3)$ [Bottom-Right]
* $P_4 = (x_4, y_4)$ [Bottom-Left]

The target canonical dimensions are determined from maximum Euclidean edge lengths:

$$W_{\text{out}} = \max\left(\sqrt{(x_2-x_1)^2 + (y_2-y_1)^2}, \sqrt{(x_3-x_4)^2 + (y_3-y_4)^2}\right)$$

$$H_{\text{out}} = \max\left(\sqrt{(x_4-x_1)^2 + (y_4-y_1)^2}, \sqrt{(x_3-x_2)^2 + (y_3-y_2)^2}\right)$$

The inverse transform mapping $\mathbf{H}^{-1}$ interpolates pixel intensities from the distorted source onto the canonical orthogonal raster grid $W_{\text{out}} \times H_{\text{out}}$.

### 3.2 Optical Densitometry and Background Subtraction

For standard colorimetric LFAs (such as colloidal gold or colored latex microparticles), antigen capture produces dark bands on a light nitrocellulose background. The signal intensity is inversely proportional to reflectance:

$$S_{\text{ROI}} = \mathcal{F}\left( \mathbf{I}[y_{\text{start}} : y_{\text{start}} + h_{\text{box}}, \, 0 : W] \right)$$

where $\mathcal{F} \in \{\text{mean}, \text{median}\}$ and $\mathbf{I}$ is the single-channel floating-point image matrix.

To eliminate spatial variations caused by non-uniform reagent rehydration or uneven lateral lighting, net optical density is calculated relative to the local membrane background:

$$\Delta S_{\text{Control}} = S_{\text{Background}} - S_{\text{Control}}$$

$$\Delta S_{T1} = S_{\text{Background}} - S_{T1}$$

$$\Delta S_{T2} = S_{\text{Background}} - S_{T2}$$

### 3.3 Normalized Test-to-Control ($T/C$) Ratio

To mitigate inter-strip variance resulting from variable sample volume loading, capillary flow rate discrepancies, or reagent lot fluctuations, analytical quantification is normalized against the internal control line:

$$R_{T1/C} = \frac{\Delta S_{T1}}{\Delta S_{\text{Control}}} = \frac{S_{\text{Background}} - S_{T1}}{S_{\text{Background}} - S_{\text{Control}}}$$

$$R_{T2/C} = \frac{\Delta S_{T2}}{\Delta S_{\text{Control}}} = \frac{S_{\text{Background}} - S_{T2}}{S_{\text{Background}} - S_{\text{Control}}}$$

---

## 4. End-to-End Operational Workflow

```
+-------------------------------------------------------------+
| Step 1: Raw Image Capture                                   |
| Unconstrained smartphone or laboratory camera photograph   |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Step 2: Perspective Rectification (Fiji / ImageJ Plugin)    |
| Script: Fiji/plugins/Four_Point_Crop.py                     |
| Actions: Multi-point ROI -> 4 corners -> Planar Homography  |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Step 3: Interactive Densitometry (Python Desktop GUI)        |
| Script: strip_analyzer.py                                   |
| Actions: Load rectified strips -> Tune ROIs -> Channel select|
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
| Step 4: Analytical Output & Telemetry                       |
| Visual: Net signal bar plots & T/C ratio graphs             |
| Tabular: Comprehensive raw, net, and ratio metrics in CSV   |
+-------------------------------------------------------------+
```

### Stage 1: Strip Rectification via Fiji / ImageJ

1. Copy `Fiji/plugins/Four_Point_Crop.py` into your Fiji `plugins/` directory, or open it directly in Fiji's Script Editor (Language: Python / Jython).
2. Open the raw LFA cassette/strip image in Fiji.
3. Select the **Multi-point Tool** from the ImageJ toolbar.
4. Click exactly 4 corner points along the boundary of the nitrocellulose membrane in strict cyclical order:
   - Point 1: Top-Left
   - Point 2: Top-Right
   - Point 3: Bottom-Right
   - Point 4: Bottom-Left
5. Execute `Four_Point_Crop.py`. The script computes the 2D homography model, applies inverse transform mapping interpolation, displays the rectified image, and prompts you to save the rectified output as PNG.

### Stage 2: Quantitative Densitometry via LFA-Analyzer GUI

1. Launch the densitometry tool:
   ```bash
   python strip_analyzer.py
   ```
2. Click **Load Image(s)** and select one or more rectified PNG/TIFF strip files.
3. Adjust the spatial integration sliders on the control panel:
   - **Box Height ($H$)**: Slit height for longitudinal intensity averaging.
   - **Control $Y$**: Vertical offset positioning the Control band (blue box).
   - **Dist to T2**: Pixel distance from Control line down to Test Line 2 (green box).
   - **Dist to T1**: Pixel distance from Control line down to Test Line 1 (red box).
   - **Dist to BG**: Pixel distance to an unreacted membrane zone for local background estimation (orange box).
4. Select measurement parameters:
   - **Channel**: Choose between Luminance, Red, Green, or Blue.
   - **Statistic**: Toggle between Mean or Median integration.
   - **Display Enhancement**: Toggle background flattening and saturation stretching for visual clarity without altering raw quantification.
5. Click **Analyze Current** to plot single-strip metrics and append records to CSV, or click **Analyze ALL Images** to execute high-throughput batch evaluation across the entire image queue.

---

## 5. Development Roadmap and Future Directions

The current version of LFA-Analyzer establishes a robust, highly reproducible densitometry engine. Active ongoing development is focused on eliminating external tool dependencies and expanding analytical support for complex assay architectures:

### 5.1 Native Integrated 4-Point Homography Perspective Cropping
* **Current State**: Planar homography perspective correction is dependent on external execution within Fiji/ImageJ (`Four_Point_Crop.py`).
* **Planned Implementation**:
  * **Interactive Manual Canvas Cropper**: Direct integration of a four-point draggable polygon overlay within the native Python GUI using Tkinter / PyQt and OpenCV (`cv2.getPerspectiveTransform`, `cv2.warpPerspective`). Users will be able to load raw smartphone photographs directly, adjust corner handles in real time, and inspect the rectified strip preview immediately within the application.
  * **Automated Strip Contour Detection**: Implementation of automated computer vision algorithms (adaptive bilateral filtering, Canny edge detection, morphological closing, and contour quadrilateral approximation via `cv2.findContours` and `cv2.approxPolyDP`) to automatically identify the nitrocellulose cassette aperture and extract the membrane without manual clicking.

### 5.2 Universal Dynamic $N$-Plex Band Architecture
* **Current State**: The spatial ROI model is hardcoded for a dual-test tri-band layout (Control Line, Test Line 2, Test Line 1, Local Background).
* **Planned Implementation**: Transition to a flexible, fully modular $N$-band detection engine supporting arbitrary multiplex configurations:
  * **Singleplex Assays**: Standard 2-band configuration ($1 \times \text{Control} + 1 \times \text{Test}$, e.g., COVID-19 rapid antigen, hCG pregnancy, troponin I).
  * **Duplex Assays**: 3-band configuration ($1 \times \text{Control} + 2 \times \text{Test}$, e.g., Influenza A/B differential screening, RSV/Flu combination panels).
  * **Triplex Assays**: 4-band configuration ($1 \times \text{Control} + 3 \times \text{Test}$, e.g., co-circulating arbovirus differentiation for Dengue, Zika, and Chikungunya).
  * **Arbitrary $N$-Plex Multiplexing**: User-definable band counts, customizable biomarker labels, individual target distance anchors, and automated peak detection along the full longitudinal cross-sectional intensity profile using 1D Gaussian smoothing and continuous wavelet transforms (CWT).

### 5.3 Quantitative Calibration and Concentration Interpolation
* Direct integration of four-parameter logistic (4PL) and five-parameter logistic (5PL) standard curve fitting modules for translating $T/C$ optical density ratios into absolute clinical concentrations ($\text{ng/mL}$ or $\text{pg/mL}$).

---

## 6. Repository Structure

```
lfa-analyzer/
|-- Fiji/
|   `-- plugins/
|       `-- Four_Point_Crop.py    # Fiji/ImageJ Jython planar homography perspective crop plugin
|-- demo.png                     # Graphical user interface overview and demonstration image
|-- requirements.txt             # Pinned Python package dependencies
|-- strip_analyzer.py            # Primary interactive Tkinter densitometry application
|-- .gitignore                   # Comprehensive Git ignore configuration
`-- README.md                    # Publication-grade technical documentation and user guide
```

---

## 7. Installation and Dependencies

### 7.1 Prerequisites
* Python 3.10 or higher
* [Fiji / ImageJ](https://fiji.sc/) (for perspective rectification pre-processing)

### 7.2 Python Environment Setup

Clone the repository and install the verified dependencies:

```bash
git clone https://github.com/Soash/lfa-analyzer.git
cd lfa-analyzer
pip install -r requirements.txt
```

#### Core Package Requirements
| Package | Version | Purpose |
| :--- | :--- | :--- |
| `numpy` | `>= 2.2.0` | High-precision `float64` array handling and statistical calculations |
| `pillow` | `>= 12.0.0` | Multi-format image ingestion (8-bit, 16-bit TIFF) and raster operations |
| `matplotlib` | `>= 3.10.0` | Diagnostic bar chart visualization and optical density telemetry plotting |

---

## 8. Authorship and Inquiries

* **Author**: Md Abu Sadat Soash
* **Institutional Affiliation**: Department of Genetic Engineering and Biotechnology, Shahjalal University of Science and Technology, Sylhet, Bangladesh
* **Correspondence**: For academic inquiries, collaborative studies, bug reports, or feature requests regarding LFA-Analyzer, please open an issue on the official [GitHub Repository](https://github.com/Soash/lfa-analyzer).
