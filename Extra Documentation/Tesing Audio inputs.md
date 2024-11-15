# Audio Methods
This was one of the major things to consider this semester was how to collect the audio. There were two main ways that could be used, analog and digital. 

<img src="/Media/Mics.jpg" width="500">

## Analog

To capture analog audio to be sent to the prossesor, the CMA-4544PF-W electret condenser microphone were used in testing. Analizing the circuit with the osiloscope was shown that there was a lot of noise. That there nosie that was getting though the simple filter that was made on the bread board. This could work but would take up valuable realestate that would be limited on the board. This was cuppled with the amount of time that would need to be spent to create a filter to reduce all tehe noice to manageble levels to prosses.

<img src="/Media/Anolog Board.jpg">

## Digital 

To capture digital audio the ICS43434 from adafuit. This works great as it was all compact and easy to bread board and test. The only problem was to creat a test that we could preform without decoding the I2S data stream, a code was needed to capture the audio. This was one of the problems as once audio was able to be captured the prossesing of the data was not preformed correctly, as it was written for the normal esp32 divkit, not the esp32 s3 devkit.

<img src="/Media/Digital Board.jpg">

