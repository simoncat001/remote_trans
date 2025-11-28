import sys
import os
import struct

def slim_bcf(input_path, output_path):
    """
    Create a slim .bcf file by removing pixel data but keeping metadata.
    This tool is designed specifically for the custom .bcf format encountered.
    """
    
    try:
        # Get file information
        file_size = os.path.getsize(input_path)
        print(f"Processing file: {input_path}")
        print(f"Original file size: {file_size / (1024*1024):.2f} MB")
        
        # Read the entire file into memory (for analysis)
        with open(input_path, 'rb') as f:
            content = f.read()
        
        # Find text sections (metadata) and binary sections (likely pixel data)
        text_sections = []
        binary_sections = []
        
        # Search for text signatures based on our previous analysis
        # We'll keep sections that contain text (likely metadata) and remove large binary blocks
        
        # Find all occurrences of text patterns (simple approach)
        current_pos = 0
        min_text_length = 10  # Minimum length of text section to consider as metadata
        
        while current_pos < len(content):
            # Check if current position contains text
            is_text_section = False
            text_start = current_pos
            
            # Look for a sequence of printable characters
            text_length = 0
            while current_pos < len(content) and (
                (32 <= content[current_pos] <= 126) or  # Printable ASCII
                content[current_pos] in b'\n\r\t'      # Whitespace
            ):
                text_length += 1
                current_pos += 1
            
            if text_length >= min_text_length:
                # This is a text section (likely metadata)
                text_sections.append((text_start, current_pos))
                is_text_section = True
            
            if not is_text_section:
                # This is a binary section (likely pixel data)
                binary_start = current_pos
                
                # Skip until we find the next text section or end of file
                while current_pos < len(content) and (
                    not (32 <= content[current_pos] <= 126 or content[current_pos] in b'\n\r\t')
                ):
                    current_pos += 1
                
                if current_pos > binary_start:
                    binary_sections.append((binary_start, current_pos))
        
        # Calculate statistics
        text_size = sum(end - start for start, end in text_sections)
        binary_size = sum(end - start for start, end in binary_sections)
        
        print(f"\nAnalysis results:")
        print(f"Text sections (metadata): {len(text_sections)} sections, {text_size / (1024*1024):.2f} MB")
        print(f"Binary sections (likely pixel data): {len(binary_sections)} sections, {binary_size / (1024*1024):.2f} MB")
        
        # Create slim file by keeping text sections and adding minimal placeholders for binary sections
        with open(output_path, 'wb') as f:
            # Copy file signature/header (first 100 bytes to ensure file format is recognized)
            header_size = min(100, len(content))
            f.write(content[:header_size])
            
            # Process remaining content
            current_pos = header_size
            
            for text_start, text_end in text_sections:
                # If there's content between current position and next text section
                if text_start > current_pos:
                    # Add a small placeholder for the removed binary data
                    placeholder = b'[PIXEL_DATA_REMOVED]\x00'
                    f.write(placeholder)
                
                # Write the text section
                f.write(content[text_start:text_end])
                current_pos = text_end
            
            # Add placeholder for any remaining binary data at the end
            if current_pos < len(content):
                placeholder = b'[PIXEL_DATA_REMOVED]\x00'
                f.write(placeholder)
        
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
        print("Usage: python slim_bcf_tool.py input.bcf output.bcf")
        sys.exit(1)
    
    slim_bcf(sys.argv[1], sys.argv[2])