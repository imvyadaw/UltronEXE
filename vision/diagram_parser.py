"""
Diagram parser
==============
Heuristic parsing of flowchart/diagram-style images (or a screen region)
into nodes and edges - no bundled diagram-understanding model, so this
works purely on shape geometry via OpenCV: contour polygon approximation
classifies each closed shape (rectangle/diamond/ellipse/triangle) as a
node, straight-line segments between two node boundaries are treated as
connecting edges, and vision/ui_detection.py's OCR pairs each node with
whatever text sits inside/near it as a label. Works well on clean, high-
contrast flowcharts (the typical whiteboard-photo or draw.io-style
export); it will do poorly on hand-drawn sketches with broken lines or
diagrams with heavy visual styling/gradients.
"""

from typing import Dict, List

try:
    import cv2
    import numpy as np

    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from vision.screen.capture import ScreenCapture
from vision.ui_detection.element_locator import UIDetector

MIN_NODE_AREA = 400


def _classify_shape(approx) -> str:
    vertices = len(approx)
    if vertices == 3:
        return "triangle"
    if vertices == 4:
        # Distinguish an upright rectangle from a diamond by how far the
        # bounding-box-vs-contour area ratio departs from a full rectangle.
        area = cv2.contourArea(approx)
        x, y, w, h = cv2.boundingRect(approx)
        fill_ratio = area / (w * h) if w and h else 0
        return "rectangle" if fill_ratio > 0.75 else "diamond"
    if vertices > 7:
        return "ellipse"
    return "polygon"


def _text_inside_or_near(box: Dict, text_regions: List[Dict]) -> str:
    fx1, fy1 = box["x"], box["y"]
    fx2, fy2 = box["x"] + box["width"], box["y"] + box["height"]
    words = []
    for region in text_regions:
        rb = region["box"]
        rcx, rcy = rb["x"] + rb["width"] / 2, rb["y"] + rb["height"] / 2
        if fx1 - 10 <= rcx <= fx2 + 10 and fy1 - 10 <= rcy <= fy2 + 10:
            words.append(region["text"])
    return " ".join(words)


class DiagramParser:
    """Detect flowchart-style nodes (boxes/diamonds/ellipses) and the
    lines connecting them, each node labeled from OCR text inside it."""

    def __init__(self):
        self._screen = ScreenCapture()
        self._ui = UIDetector()

    def parse(self, image=None) -> Dict:
        if not HAS_CV2:
            return {"error": "opencv-python not installed - run: pip install opencv-python-headless"}

        if image is None:
            image = self._screen.capture()
            if isinstance(image, dict):
                return image

        text_result = self._ui.find_text_regions(image=image)
        text_regions = text_result.get("regions", []) if "error" not in text_result else []

        try:
            frame = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            nodes = []
            for i, contour in enumerate(contours):
                area = cv2.contourArea(contour)
                if area < MIN_NODE_AREA:
                    continue
                x, y, w, h = cv2.boundingRect(contour)
                perimeter = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
                box = {"x": x, "y": y, "width": w, "height": h}
                nodes.append(
                    {
                        "id": f"node_{i}",
                        "shape": _classify_shape(approx),
                        "box": box,
                        "label": _text_inside_or_near(box, text_regions),
                    }
                )

            # Straight connector segments between node boundaries (not
            # inside any node itself) - a rough stand-in for "edges".
            edges = []
            edges_img = cv2.Canny(gray, 50, 150)
            lines = cv2.HoughLinesP(edges_img, 1, np.pi / 180, threshold=60, minLineLength=40, maxLineGap=8)
            if lines is not None:
                for line in lines[:200]:
                    x1, y1, x2, y2 = line[0]
                    start_node = self._node_at_point(nodes, x1, y1)
                    end_node = self._node_at_point(nodes, x2, y2)
                    if start_node and end_node and start_node != end_node:
                        edges.append({"from": start_node, "to": end_node})

            # De-duplicate edges (Hough tends to fire multiple near-parallel
            # segments for one visual line).
            unique_edges = list({(e["from"], e["to"]) for e in edges})
            edges = [{"from": f, "to": t} for f, t in unique_edges]

            return {"node_count": len(nodes), "nodes": nodes, "edge_count": len(edges), "edges": edges}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _node_at_point(nodes: List[Dict], x: int, y: int, margin: int = 6):
        for node in nodes:
            b = node["box"]
            if (
                b["x"] - margin <= x <= b["x"] + b["width"] + margin
                and b["y"] - margin <= y <= b["y"] + b["height"] + margin
            ):
                return node["id"]
        return None


_instance: "DiagramParser" = None


def get_diagram_parser() -> DiagramParser:
    global _instance
    if _instance is None:
        _instance = DiagramParser()
    return _instance
