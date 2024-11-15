# Audio Methods

This was one of the major things to consider this semester was how to collect the audio. There were two main ways that could be used, analog and digital.

<img src="/Media/Mics.jpg" width="500">

## Analog

To capture analog audio to be sent to the processor, the CMA-4544PF-W electret condenser microphone was used in testing. Analyzing the circuit with the oscilloscope was shown that there was a lot of noise. That there was noise that was getting through the simple filter that was made on the breadboard. This could work but would take up valuable real estate that would be limited on the board. This was coupled with the amount of time that would need to be spent to create a filter to reduce all the noise to manageable levels to process.

<img src="/Media/Anolog Board.jpg">

## Digital

To capture digital audio the ICS43434 from adafruit. This works great as it was all compact and easy to breadboard and test. The only problem was to create a test that we could perform without decoding the I2S data stream, a code was needed to capture the audio. This was one of the problems as once audio was able to be captured the processing of the data was not performed correctly, as it was written for the normal esp32 dev kit, not the esp32 s3 devkit.

<img src="/Media/Digital Board.jpg">
