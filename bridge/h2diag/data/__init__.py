"""① DATA IN: getting messages from the robot (DDS) or from recordings on disk.

Nothing here interprets messages; that's processing/. Lower layer: must not
import processing/, output/ or views/ (tests/test_layers.py checks).

Both sources expose the same interface (duck typing):

    source.topics   -> list of topic names it can deliver
    source.stats    -> {topic: TopicStats}, updated as messages arrive
    source.now()    -> the source's clock (monotonic seconds; virtual for replay)
    source.poll(dt) -> [(topic, data_dict)] newest message per topic since last poll
    source.live     -> True for the robot, False for a recording
    source.done     -> True once a non-looping replay has run out

READ-ONLY: only DDS readers are ever created. tests/test_pipeline.py checks it.
"""
