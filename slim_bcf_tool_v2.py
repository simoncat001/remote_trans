import sys
import os

def slim_bcf(input_path, output_path):
    """
    Create a slim .bcf file by removing pixel data but keeping metadata.
    This version processes the file in chunks for better memory efficiency.
    """
    
    try:
        # Get file information
        file_size = os.path.getsize(input_path)
        print(f"Processing file: {input_path}")
        print(f"Original file size: {file_size / (1024*1024):.2f} MB")
        
        # Chunk processing parameters
        chunk_size = 1024 * 1024  # 1MB chunks
        min_text_length = 10     # Minimum length of text section to consider as metadata
        
        with open(input_path, 'rb') as infile, open(output_path, 'wb') as outfile:
            # Copy file signature/header (first 100 bytes)
            header = infile.read(100)
            outfile.write(header)
            
            # Process the rest of the file in chunks
            buffer = b''
            last_chunk = False
            
            while not last_chunk:
                # Read next chunk
                chunk = infile.read(chunk_size)
                if not chunk:
                    last_chunk = True
                
                # Add to buffer
                buffer += chunk
                
                # Process buffer
                pos = 0
                buffer_len = len(buffer)
                
                while pos < buffer_len:
                    # Check if current position is part of text
                    if pos + min_text_length <= buffer_len:
                        # Look for text sequence
                        text_start = pos
                        text_end = pos
                        
                        while text_end < buffer_len and (
                            (32 <= buffer[text_end] <= 126) or  # Printable ASCII
                            buffer[text_end] in b'\n\r\t'      # Whitespace
                        ):
                            text_end += 1
                        
                        if text_end - text_start >= min_text_length:
                            # This is text (keep it)
                            outfile.write(buffer[pos:text_end])
                            pos = text_end
                        else:
                            # This is binary (skip it)
                            # Find next text section
                            while pos < buffer_len and (
                                not (32 <= buffer[pos] <= 126 or buffer[pos] in b'\n\r\t')
                            ):
                                pos += 1
                    else:
                        # Not enough data in buffer, keep for next iteration
                        break
                
                # Keep remaining buffer for next iteration
                buffer = buffer[pos:]
            
            # Process any remaining data
            if buffer:
                # Check if remaining buffer is text
                text_count = sum(1 for b in buffer if 32 <= b <= 126 or b in b'\n\r\t')
                if text_count / len(buffer) > 0.8:  # If more than 80% is text, keep it
                    outfile.write(buffer)
                else:
                    # Otherwise, add placeholder
                    outfile.write(b'[PIXEL_DATA_REMOVED]\x00')
        
        # Verify the result
        new_size = os.path.getsize(output_path)
        print(f"\n✔ Done. Slim .bcf saved to:\n{output_path}")
        print(f"New file size: {new_size / (1024*1024):.2f} MB")
        print(f"Reduction: {((file_size - new_size) / file_size * 100):.2f}%")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python slim_bcf_tool_v2.py input.bcf output.bcf")
        sys.exit(1)
    
    slim_bcf(sys.argv[1], sys.argv[2])