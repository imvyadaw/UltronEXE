"""Design automations: Photoshop, Illustrator, Canva, Figma, GIMP."""

from apps.design.photoshop import PhotoshopApp
from apps.design.illustrator import IllustratorApp
from apps.design.canva import CanvaApp
from apps.design.figma import FigmaApp
from apps.design.gimp import GimpApp

__all__ = ["PhotoshopApp", "IllustratorApp", "CanvaApp", "FigmaApp", "GimpApp"]
