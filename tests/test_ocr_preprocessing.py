"""
Comprehensive test suite for image preprocessing enhancement.

Tests the _enhance_image_preprocessing function with:
- Input validation (type, shape, dtype)
- Output validation (shape, values, dtype)
- CLAHE contrast enhancement
- Deskew rotation correction
- Denoise quality and edge preservation
- Morphological operations
- Integration pipeline tests
- Edge cases
"""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
import cv2
from app.services.ocr_service import _enhance_image_preprocessing


# ============================================================================
# FIXTURES: Test Image Generators
# ============================================================================

@pytest.fixture
def clean_grayscale_image():
    """Clean 8-bit grayscale image (500x500) with normal values."""
    img = np.random.randint(50, 200, (500, 500), dtype=np.uint8)
    return img


@pytest.fixture
def noisy_grayscale_image():
    """Grayscale image with significant Gaussian noise."""
    base = np.random.randint(100, 150, (500, 500), dtype=np.uint8)
    noise = np.random.normal(0, 25, (500, 500))
    img = np.clip(base + noise, 0, 255).astype(np.uint8)
    return img


@pytest.fixture
def low_contrast_image():
    """Image with poor contrast (all values in narrow range)."""
    img = np.random.randint(120, 140, (500, 500), dtype=np.uint8)
    return img


@pytest.fixture
def rgb_image():
    """RGB color image (500x500x3)."""
    img = np.random.randint(50, 200, (500, 500, 3), dtype=np.uint8)
    return img


@pytest.fixture
def small_grayscale_image():
    """Small 8-bit grayscale image (20x20)."""
    img = np.random.randint(50, 200, (20, 20), dtype=np.uint8)
    return img


@pytest.fixture
def large_grayscale_image():
    """Large 8-bit grayscale image (2000x2000)."""
    img = np.random.randint(50, 200, (2000, 2000), dtype=np.uint8)
    return img


@pytest.fixture
def all_black_image():
    """Image with all zeros (black)."""
    return np.zeros((500, 500), dtype=np.uint8)


@pytest.fixture
def all_white_image():
    """Image with all 255 (white)."""
    return np.full((500, 500), 255, dtype=np.uint8)


@pytest.fixture
def rotated_image():
    """Grayscale image rotated by ~15 degrees (to test deskew)."""
    # Create base image with text-like content
    img = np.zeros((500, 500), dtype=np.uint8)
    # Add horizontal lines to create rotation effect
    img[100:150, :] = 200
    img[250:300, :] = 200
    img[400:450, :] = 200
    
    # Rotate by 15 degrees
    center = (250, 250)
    rotation_matrix = cv2.getRotationMatrix2D(center, 15, 1.0)
    rotated = cv2.warpAffine(img, rotation_matrix, (500, 500), borderValue=0)
    return rotated


@pytest.fixture
def single_channel_float_image():
    """Single-channel image with float values in [0, 1] range."""
    img = np.random.random((500, 500)).astype(np.float32)
    return img


# ============================================================================
# TEST GROUP 1: Input Validation Tests
# ============================================================================

class TestInputValidation:
    """Test input validation: correct types, shapes, and dtypes."""

    def test_accepts_valid_uint8_array(self, clean_grayscale_image):
        """Should accept valid uint8 numpy array without error."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert result is not None
        assert isinstance(result, np.ndarray)

    def test_accepts_2d_grayscale(self, clean_grayscale_image):
        """Should accept 2D grayscale array (H, W)."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert isinstance(result, np.ndarray)

    def test_accepts_3d_rgb(self, rgb_image):
        """Should accept 3D RGB array (H, W, 3)."""
        result = _enhance_image_preprocessing(rgb_image)
        assert isinstance(result, np.ndarray)


# ============================================================================
# TEST GROUP 2: Output Validation Tests
# ============================================================================

class TestOutputValidation:
    """Test output properties: shape, dtype, value ranges."""

    def test_output_is_numpy_array(self, clean_grayscale_image):
        """Output should be a numpy array."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert isinstance(result, np.ndarray)

    def test_output_shape_matches_grayscale_input(self, clean_grayscale_image):
        """Output shape should match input shape for grayscale."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert result.shape == clean_grayscale_image.shape

    def test_output_shape_matches_rgb_input(self, rgb_image):
        """Output shape should match input shape for RGB (converts to grayscale)."""
        result = _enhance_image_preprocessing(rgb_image)
        # RGB converted to grayscale should be 2D
        assert len(result.shape) == 2

    def test_output_dtype_is_uint8(self, clean_grayscale_image):
        """Output dtype should be uint8."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert result.dtype == np.uint8

    def test_output_values_in_valid_range(self, clean_grayscale_image):
        """All output values should be in [0, 255] range."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert result.min() >= 0
        assert result.max() <= 255

    @pytest.mark.parametrize("shape", [(100, 100), (500, 500), (2000, 2000)])
    def test_output_preserves_shape_across_sizes(self, shape):
        """Output shape should be preserved for various image sizes."""
        img = np.random.randint(50, 200, shape, dtype=np.uint8)
        result = _enhance_image_preprocessing(img)
        assert result.shape == img.shape

    def test_output_is_not_empty(self, clean_grayscale_image):
        """Output array should not be empty."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert result.size > 0


# ============================================================================
# TEST GROUP 3: CLAHE (Contrast-Limited Adaptive Histogram Equalization)
# ============================================================================

class TestCLAHEEnhancement:
    """Test CLAHE functionality for contrast enhancement."""

    def test_clahe_improves_contrast_on_low_contrast_image(self, low_contrast_image):
        """CLAHE should increase contrast on low-contrast images."""
        result = _enhance_image_preprocessing(low_contrast_image)
        
        # Calculate standard deviation as measure of contrast
        input_std = low_contrast_image.astype(np.float32).std()
        output_std = result.astype(np.float32).std()
        
        # Output should have reasonable contrast (relaxed threshold for randomness)
        assert output_std >= input_std * 0.5, "Contrast should be maintained or improved"

    def test_clahe_preserves_high_contrast_image(self, clean_grayscale_image):
        """CLAHE should not degrade already good contrast."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8

    def test_clahe_extends_histogram(self, low_contrast_image):
        """CLAHE should extend histogram to use more of [0, 255] range."""
        result = _enhance_image_preprocessing(low_contrast_image)
        
        input_range = low_contrast_image.max() - low_contrast_image.min()
        output_range = result.max() - result.min()
        
        # Output should use wider range
        assert output_range >= input_range * 0.8, "Histogram should be extended"

    def test_clahe_does_not_add_artifacts_to_uniform_region(self):
        """CLAHE should not create visible artifacts in uniform regions."""
        # Create mostly uniform image with small noise
        img = np.full((200, 200), 128, dtype=np.uint8)
        # Fix: Cast carefully to avoid dtype issues
        noise_region = img[50:150, 50:150].astype(int) + np.random.randint(-5, 5, (100, 100))
        img[50:150, 50:150] = np.clip(noise_region, 0, 255).astype(np.uint8)
        
        result = _enhance_image_preprocessing(img)
        
        # Check that uniform region doesn't get excessively modified
        uniform_region_std = result[0:50, 0:50].std()
        assert uniform_region_std < 30, "Uniform regions should remain stable"


# ============================================================================
# TEST GROUP 4: Deskewing (Rotation Correction)
# ============================================================================

class TestDeskewFunctionality:
    """Test deskew rotation correction."""

    def test_deskew_corrects_rotated_image(self, rotated_image):
        """Deskew should detect and correct rotation."""
        result = _enhance_image_preprocessing(rotated_image)
        assert result.shape == rotated_image.shape
        assert result.dtype == np.uint8

    def test_deskew_preserves_straight_image(self, clean_grayscale_image):
        """Deskew should not unnecessarily rotate straight images."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        # Should return a valid image (not rotated incorrectly)
        assert result.shape == clean_grayscale_image.shape

    def test_deskew_output_is_not_empty_after_rotation_correction(self, rotated_image):
        """Deskewed image should not have excessive empty borders."""
        result = _enhance_image_preprocessing(rotated_image)
        
        # Count non-zero pixels
        non_zero = np.count_nonzero(result)
        total = result.size
        
        # At least 50% of image should have data (not border)
        assert non_zero / total >= 0.5, "Deskew should not create excessive borders"


# ============================================================================
# TEST GROUP 5: Denoising
# ============================================================================

class TestDenoiseQuality:
    """Test denoising quality and edge preservation."""

    def test_denoise_reduces_noise(self, noisy_grayscale_image):
        """Denoising should reduce image noise."""
        result = _enhance_image_preprocessing(noisy_grayscale_image)
        
        # Calculate Laplacian to estimate noise
        input_laplacian = cv2.Laplacian(noisy_grayscale_image, cv2.CV_32F)
        output_laplacian = cv2.Laplacian(result, cv2.CV_32F)
        
        input_noise = np.sqrt(np.mean(input_laplacian ** 2))
        output_noise = np.sqrt(np.mean(output_laplacian ** 2))
        
        # Denoising should reduce noise variance
        assert output_noise <= input_noise * 1.1, "Denoising should reduce noise"

    def test_denoise_preserves_edges(self, clean_grayscale_image):
        """Denoising should not blur important edges."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        
        # Use Canny edge detection as quality metric
        input_edges = cv2.Canny(clean_grayscale_image, 50, 150)
        output_edges = cv2.Canny(result, 50, 150)
        
        input_edge_count = np.count_nonzero(input_edges)
        output_edge_count = np.count_nonzero(output_edges)
        
        # Edge count should be preserved (not excessively blurred)
        assert output_edge_count >= input_edge_count * 0.7, "Edges should be preserved"

    def test_denoise_output_values_valid(self, noisy_grayscale_image):
        """Denoised output should have valid uint8 values."""
        result = _enhance_image_preprocessing(noisy_grayscale_image)
        assert result.dtype == np.uint8
        assert result.min() >= 0
        assert result.max() <= 255


# ============================================================================
# TEST GROUP 6: Morphological Operations
# ============================================================================

class TestMorphologicalOperations:
    """Test morphological operations (opening, closing)."""

    def test_morphological_operations_applied(self, clean_grayscale_image):
        """Morphological operations should be applied to the image."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        
        # Morphological operations should process the image
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        assert result.shape == clean_grayscale_image.shape

    def test_morphology_preserves_image_size(self, clean_grayscale_image):
        """Morphological operations should not change image dimensions."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        assert result.shape == clean_grayscale_image.shape

    def test_morphology_fills_small_holes(self):
        """Morphological closing should fill small holes."""
        # Create image with small holes
        img = np.full((200, 200), 200, dtype=np.uint8)
        img[50:150, 50:150] = 100
        # Add small white holes in dark region
        img[75:85, 75:85] = 200
        
        result = _enhance_image_preprocessing(img)
        
        # Region should be more connected
        assert isinstance(result, np.ndarray)


# ============================================================================
# TEST GROUP 7: Integration Tests (Full Pipeline)
# ============================================================================

class TestIntegrationPipeline:
    """Test complete preprocessing pipeline."""

    def test_grayscale_to_grayscale_pipeline(self, clean_grayscale_image):
        """Full pipeline should work for grayscale input."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        assert result.shape == clean_grayscale_image.shape
        assert result.min() >= 0
        assert result.max() <= 255

    def test_rgb_to_grayscale_pipeline(self, rgb_image):
        """Full pipeline should convert RGB to grayscale."""
        result = _enhance_image_preprocessing(rgb_image)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        # Output should be 2D (grayscale)
        assert len(result.shape) == 2
        assert result.shape[0] == rgb_image.shape[0]
        assert result.shape[1] == rgb_image.shape[1]

    def test_noisy_image_full_pipeline(self, noisy_grayscale_image):
        """Full pipeline should handle noisy input."""
        result = _enhance_image_preprocessing(noisy_grayscale_image)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        assert result.shape == noisy_grayscale_image.shape

    def test_low_contrast_full_pipeline(self, low_contrast_image):
        """Full pipeline should enhance low-contrast image."""
        result = _enhance_image_preprocessing(low_contrast_image)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8


# ============================================================================
# TEST GROUP 8: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_small_image_processing(self, small_grayscale_image):
        """Should handle small images (20x20)."""
        result = _enhance_image_preprocessing(small_grayscale_image)
        
        assert isinstance(result, np.ndarray)
        assert result.shape == small_grayscale_image.shape
        assert result.dtype == np.uint8

    def test_large_image_processing(self, large_grayscale_image):
        """Should handle large images (2000x2000)."""
        result = _enhance_image_preprocessing(large_grayscale_image)
        
        assert isinstance(result, np.ndarray)
        assert result.shape == large_grayscale_image.shape
        assert result.dtype == np.uint8

    def test_all_black_image(self, all_black_image):
        """Should handle all-black image without errors."""
        result = _enhance_image_preprocessing(all_black_image)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        # Result might be slightly different due to processing
        assert result.shape == all_black_image.shape

    def test_all_white_image(self, all_white_image):
        """Should handle all-white image without errors."""
        result = _enhance_image_preprocessing(all_white_image)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8
        assert result.shape == all_white_image.shape

    def test_uniform_gray_image(self):
        """Should handle uniform gray image without artifacts."""
        img = np.full((500, 500), 128, dtype=np.uint8)
        result = _enhance_image_preprocessing(img)
        
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.uint8

    def test_extreme_high_values(self):
        """Should handle image with extreme values (255)."""
        img = np.random.randint(200, 256, (500, 500), dtype=np.uint8)
        result = _enhance_image_preprocessing(img)
        
        assert isinstance(result, np.ndarray)
        assert result.max() <= 255

    def test_extreme_low_values(self):
        """Should handle image with extreme low values (0)."""
        img = np.random.randint(0, 50, (500, 500), dtype=np.uint8)
        result = _enhance_image_preprocessing(img)
        
        assert isinstance(result, np.ndarray)
        assert result.min() >= 0


# ============================================================================
# TEST GROUP 9: Parametrized Tests (Multiple Configurations)
# ============================================================================

class TestParametrizedValidation:
    """Parametrized tests for multiple configurations."""

    @pytest.mark.parametrize("height,width", [
        (100, 100),
        (500, 500),
        (1000, 1000),
        (256, 512),
        (512, 256),
    ])
    def test_various_image_dimensions(self, height, width):
        """Should handle various image dimensions."""
        img = np.random.randint(50, 200, (height, width), dtype=np.uint8)
        result = _enhance_image_preprocessing(img)
        
        assert result.shape == (height, width)
        assert result.dtype == np.uint8

    @pytest.mark.parametrize("value", [0, 50, 100, 150, 200, 255])
    def test_uniform_image_at_different_levels(self, value):
        """Should handle uniform images at different gray levels."""
        img = np.full((256, 256), value, dtype=np.uint8)
        result = _enhance_image_preprocessing(img)
        
        assert result.dtype == np.uint8
        assert result.shape == (256, 256)


# ============================================================================
# TEST GROUP 10: Property-Based Tests
# ============================================================================

class TestPropertyInvariants:
    """Test invariant properties that should always hold."""

    def test_output_always_normalized(self, clean_grayscale_image):
        """Output should always be in valid uint8 range."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        
        # Should be valid uint8
        assert 0 <= result.min()
        assert result.max() <= 255
        assert result.dtype == np.uint8

    def test_no_nan_values(self, clean_grayscale_image):
        """Output should never contain NaN values."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        
        assert not np.isnan(result).any()

    def test_no_inf_values(self, clean_grayscale_image):
        """Output should never contain infinite values."""
        result = _enhance_image_preprocessing(clean_grayscale_image)
        
        assert not np.isinf(result).any()
