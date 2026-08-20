"""FlyThrough: anchored AI property flythroughs from an agent's listing photos.

The product constraint, in one sentence: every shot begins and ends on a REAL
photograph of the property, and the model only generates the travel in between.
That is what keeps the house in the video the same house that is for sale.
"""

__version__ = "1.0.0"

from .assemble import Deliverables, deliver
from .cost import Quote, quote
from .planner import Plan, Shot, build_plan
from .render import Job, OpenArtAdapter, QueueAdapter, build_jobs, write_manifest
from .rooms import Room, resolve

__all__ = [
    "__version__",
    "Plan", "Shot", "build_plan",
    "Room", "resolve",
    "Quote", "quote",
    "Job", "OpenArtAdapter", "QueueAdapter", "build_jobs", "write_manifest",
    "Deliverables", "deliver",
]
