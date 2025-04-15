# Add the binary file as a source
idf_component_register(SRCS "continuous_read_main.c"
                       INCLUDE_DIRS "."
                       EMBED_FILES "audio_file.bin")  # Add the path to your binary file
