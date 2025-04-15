import librosa
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks
from pydub import AudioSegment

# Step 1: Load the audio files using librosa
audio_file_1 = 'audioFiles/TalkingLeft.wav'
audio_file_2 = 'audioFiles/TalkingRight.wav'

y1, sr1 = librosa.load(audio_file_1, sr=48000)
y2, sr2 = librosa.load(audio_file_2, sr=48000)

# Step 2: Detect Peaks (Claps)
# Use the amplitude of the signal to find peaks, you can adjust height to tune peak detection
peaks1, _ = find_peaks(np.abs(y1), height=0.01, distance=sr1//4)
peak_values_y2 = []
peak_values_y1 = []
for index in peaks1:
    peak_values_y1.append(y1[index])
    peak_values_y2.append(y2[index])

# Visualize the peaks
plt.figure(figsize=(15, 5))
plt.plot(y1, label="Track 1")
plt.plot(peaks1, np.abs(peak_values_y1), "x", label="AMP 1")
plt.plot(y2, label="Track 2")
plt.plot(peaks1, np.abs(peak_values_y2), "o", label="AMP 2")
plt.legend()

# Save the plot to a file instead of displaying it
plt.savefig("peaks_plot.png")

i = 0
while i < len(peak_values_y1):
    val1 = np.abs(peak_values_y1[i])
    val2 = np.abs(peak_values_y2[i])
    if val1 > val2:
        difference = librosa.amplitude_to_db(val1 - val2)*-1
        print(f"Audio 1 is louder by {difference:.2f}")
    elif val2 > val1:
        difference = val2 - val1
        print(f"Audio 2 is louder by {difference:.2f}")
    else:
        print("Both audios have the same loudness.")
    i += 1
# Step 3: Calculate the time offset between the first peaks
time_offset = (peaks2[0] - peaks1[0]) / sr1

print(f"Time offset between first claps: {time_offset} seconds")

# Step 4: Shift one audio to align with the other
# Convert time offset to milliseconds
time_offset_ms = time_offset * 1000

# Print the time delay in ms to the termnial
print(f"Calculated time delay between first claps: {time_offset_ms:.2f} ms")

# Use pydub to handle shifting and saving the files
audio1 = AudioSegment.from_wav(audio_file_1)
audio2 = AudioSegment.from_wav(audio_file_2)

if time_offset_ms > 0:
    # Shift the second track forward by time_offset_ms
    aligned_audio2 = AudioSegment.silent(duration=time_offset_ms) + audio2
    aligned_audio1 = audio1
else:
    # Shift the first track forward by abs(time_offset_ms)
    aligned_audio1 = AudioSegment.silent(duration=abs(time_offset_ms)) + audio1
    aligned_audio2 = audio2

# Step 5: Save the aligned tracks (or combine them)
aligned_audio1.export("audioFiles/export/aligned_track1.wav", format="wav")
aligned_audio2.export("audioFiles/export/aligned_track2.wav", format="wav")

# You could also mix the two tracks together if needed:
combined = aligned_audio1.overlay(aligned_audio2)
combined.export("audioFiles/export/combined_aligned.wav", format="wav")

