import h5py
import sys
import os

def strip_bcf(input_path, output_path):
    """
    Create a slim .bcf file that removes pixel-heavy datasets such as:
    - Spectra
    - Element maps
    - EBSD patterns
    - Raw pixel matrices
    but keeps metadata tree structures.
    """

    pixel_keywords = [
        "Spectra",
        "Maps",
        "ElementMaps",
        "RawData",
        "EBSD",
        "Kikuchi",
        "Pattern",
        "PatternData",
        "Frames",
        "Linescan",
        "Counts",
        "Intensity",
    ]

    def is_pixel_dataset(name):
        """Check if a dataset name suggests heavy pixel data."""
        name_low = name.lower()
        return any(key.lower() in name_low for key in pixel_keywords)

    try:
        with h5py.File(input_path, "r") as src, h5py.File(output_path, "w") as dst:
            print(f"Processing file: {input_path}")
            print(f"File size: {os.path.getsize(input_path) / (1024*1024):.2f} MB")

            def copy_group(src_group, dst_group):
                # Copy attributes
                for key, value in src_group.attrs.items():
                    dst_group.attrs[key] = value

                # Copy datasets
                for name, item in src_group.items():
                    full_path = item.name

                    if isinstance(item, h5py.Group):
                        # Create destination group and recurse
                        new_group = dst_group.create_group(name)
                        copy_group(item, new_group)

                    elif isinstance(item, h5py.Dataset):
                        if is_pixel_dataset(full_path):
                            print(f"Removing dataset: {full_path}")
                            # Instead of copying large array, create an empty dataset
                            dst_group.create_dataset(name, data=[])
                        else:
                            try:
                                # Copy small / metadata datasets
                                dst_group.create_dataset(name, data=item[()])
                                print(f"Copied metadata dataset: {full_path}")
                            except Exception as e:
                                print(f"Error copying {full_path}: {e}")
                                # If copying fails, create an empty dataset
                                dst_group.create_dataset(name, data=[])

            # Start recursive copy
            copy_group(src, dst)

        print(f"\n✔ Done. Slim .bcf saved to:\n{output_path}")
        print(f"New file size: {os.path.getsize(output_path) / (1024*1024):.2f} MB")
        
    except Exception as e:
        print(f"Error processing file: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python strip_bcf_tool.py input.bcf output.bcf")
        sys.exit(1)

    strip_bcf(sys.argv[1], sys.argv[2])