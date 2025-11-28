import sys
import os

def split_file(input_path, output_dir, num_parts=100):
    """
    将大文件分割成指定数量的小块
    
    Args:
        input_path: 输入文件路径
        output_dir: 输出目录路径
        num_parts: 要分割的块数（默认100）
    """
    
    try:
        # 获取文件信息
        file_size = os.path.getsize(input_path)
        print(f"处理文件: {input_path}")
        print(f"文件大小: {file_size / (1024*1024):.2f} MB")
        print(f"计划分割成: {num_parts} 块")
        
        # 计算每块的大小
        part_size = file_size // num_parts
        
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 获取文件名（不含扩展名）
        base_name = os.path.basename(input_path)
        name_without_ext, ext = os.path.splitext(base_name)
        
        # 分割文件
        part_num = 1
        bytes_written = 0
        
        with open(input_path, 'rb') as infile:
            while bytes_written < file_size:
                # 计算当前块的实际大小
                current_part_size = min(part_size, file_size - bytes_written)
                
                # 构建输出文件名
                output_filename = f"{name_without_ext}_part{part_num:03d}{ext}"
                output_path = os.path.join(output_dir, output_filename)
                
                # 读取并写入当前块
                print(f"分割块 {part_num}/{num_parts}: {output_filename} ({current_part_size / (1024*1024):.2f} MB)")
                
                with open(output_path, 'wb') as outfile:
                    # 分小块读取写入，避免内存问题
                    remaining = current_part_size
                    chunk_size = 1024 * 1024  # 1MB 小块
                    
                    while remaining > 0:
                        read_size = min(chunk_size, remaining)
                        data = infile.read(read_size)
                        outfile.write(data)
                        remaining -= read_size
                
                # 更新进度
                bytes_written += current_part_size
                part_num += 1
        
        print(f"\n✅ 分割完成！")
        print(f"原始文件大小: {file_size / (1024*1024):.2f} MB")
        print(f"每块平均大小: {part_size / (1024*1024):.2f} MB")
        print(f"实际分割块数: {part_num - 1}")
        print(f"所有块都保存在: {output_dir}")
        
    except Exception as e:
        print(f"处理文件时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python split_bcf_file.py input.bcf output_directory [num_parts]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_dir = sys.argv[2]
    num_parts = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    
    split_file(input_path, output_dir, num_parts)
