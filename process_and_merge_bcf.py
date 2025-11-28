import sys
import os
import glob

def process_bcf_chunk(input_path, output_path):
    """
    处理单个.bcf文件块，删除像素内容，保留元数据和样本扫描信息
    
    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
    """
    
    try:
        # 获取文件信息
        file_size = os.path.getsize(input_path)
        print(f"处理文件块: {os.path.basename(input_path)}")
        print(f"块大小: {file_size / (1024*1024):.2f} MB")
        
        # 使用内存效率高的方式处理文件
        chunk_size = 65536  # 64KB chunks
        min_text_length = 10  # 最小文本长度，视为元数据
        
        with open(input_path, 'rb') as infile, open(output_path, 'wb') as outfile:
            buffer = b''
            
            while True:
                # 读取下一个块
                chunk = infile.read(chunk_size)
                if not chunk:
                    break
                
                # 添加到缓冲区
                buffer += chunk
                
                # 处理缓冲区
                pos = 0
                buffer_len = len(buffer)
                
                while pos < buffer_len:
                    # 检查当前位置是否为文本
                    if pos + min_text_length <= buffer_len:
                        # 查找文本序列
                        text_start = pos
                        text_end = pos
                        
                        while text_end < buffer_len and (
                            (32 <= buffer[text_end] <= 126) or  # 可打印ASCII
                            buffer[text_end] in b'\n\r\t'      # 空白字符
                        ):
                            text_end += 1
                        
                        if text_end - text_start >= min_text_length:
                            # 这是文本（保留）
                            outfile.write(buffer[pos:text_end])
                            pos = text_end
                        else:
                            # 这是二进制数据（跳过）
                            # 查找下一个文本部分
                            while pos < buffer_len and (
                                not (32 <= buffer[pos] <= 126 or buffer[pos] in b'\n\r\t')
                            ):
                                pos += 1
                    else:
                        # 缓冲区数据不足，保留到下一次迭代
                        break
                
                # 保留剩余缓冲区内容用于下一次迭代
                buffer = buffer[pos:]
            
            # 处理剩余数据
            if buffer:
                # 检查剩余缓冲区是否为文本
                text_count = sum(1 for b in buffer if 32 <= b <= 126 or b in b'\n\r\t')
                if text_count / len(buffer) > 0.8:  # 如果80%以上是文本，保留
                    outfile.write(buffer)
        
        # 验证结果
        new_size = os.path.getsize(output_path)
        print(f"处理后大小: {new_size / (1024*1024):.2f} MB")
        print(f"压缩比例: {((file_size - new_size) / file_size * 100):.2f}%")
        
        return True
        
    except Exception as e:
        print(f"处理文件块时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def process_all_chunks(input_dir, output_dir):
    """
    处理指定目录下的所有.bcf文件块
    
    Args:
        input_dir: 输入目录路径
        output_dir: 输出目录路径
    """
    
    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有.bcf文件块（按名称排序）
    chunk_files = sorted(glob.glob(os.path.join(input_dir, "*.bcf")))
    
    print(f"找到 {len(chunk_files)} 个文件块需要处理")
    
    processed_files = []
    
    # 处理每个文件块
    for i, chunk_file in enumerate(chunk_files, 1):
        print(f"\n=== 处理块 {i}/{len(chunk_files)} ===")
        
        # 构建输出文件名
        base_name = os.path.basename(chunk_file)
        output_file = os.path.join(output_dir, f"processed_{base_name}")
        
        # 处理文件块
        if process_bcf_chunk(chunk_file, output_file):
            processed_files.append(output_file)
        
    return processed_files

def merge_files(input_files, output_path):
    """
    合并多个文件为一个文件
    
    Args:
        input_files: 输入文件列表
        output_path: 输出文件路径
    """
    
    try:
        total_size = 0
        
        with open(output_path, 'wb') as outfile:
            for i, input_file in enumerate(input_files, 1):
                file_size = os.path.getsize(input_file)
                total_size += file_size
                
                print(f"合并文件 {i}/{len(input_files)}: {os.path.basename(input_file)} ({file_size / (1024*1024):.2f} MB)")
                
                # 分块读取并写入，避免内存问题
                with open(input_file, 'rb') as infile:
                    while True:
                        chunk = infile.read(65536)  # 64KB chunks
                        if not chunk:
                            break
                        outfile.write(chunk)
        
        print(f"\n✅ 合并完成！")
        print(f"输出文件: {output_path}")
        print(f"总大小: {total_size / (1024*1024):.2f} MB")
        
        return True
        
    except Exception as e:
        print(f"合并文件时出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """
    主函数：处理分割后的.bcf文件块，删除像素内容，合并成新文件
    """
    
    if len(sys.argv) < 3:
        print("用法: python process_and_merge_bcf.py input_chunk_dir output_merged_file.bcf")
        print("示例: python process_and_merge_bcf.py data/SEM/split_parts data/SEM/1_metadata_only.bcf")
        sys.exit(1)
    
    input_chunk_dir = sys.argv[1]
    output_merged_file = sys.argv[2]
    
    print("="*60)
    print("BCF文件处理与合并工具")
    print("功能：删除像素内容，保留元数据和样本扫描信息")
    print("="*60)
    
    # 创建临时处理目录
    temp_process_dir = os.path.join(os.path.dirname(output_merged_file), "temp_processed_chunks")
    os.makedirs(temp_process_dir, exist_ok=True)
    
    try:
        # 第一步：处理所有文件块
        print("\n📋 第一步：处理所有文件块，删除像素内容...")
        processed_files = process_all_chunks(input_chunk_dir, temp_process_dir)
        
        if not processed_files:
            print("❌ 没有成功处理的文件块，任务中止")
            sys.exit(1)
        
        print(f"\n📊 处理统计：")
        print(f"- 总文件块数: {len(glob.glob(os.path.join(input_chunk_dir, "*.bcf")))}")
        print(f"- 成功处理: {len(processed_files)}")
        
        # 第二步：合并处理后的文件块
        print("\n🔄 第二步：合并处理后的文件块...")
        if merge_files(processed_files, output_merged_file):
            print("\n🎉 任务完成！")
            print(f"\n📁 最终生成的元数据文件：")
            print(f"- {output_merged_file}")
            print(f"- 大小: {os.path.getsize(output_merged_file) / (1024*1024):.2f} MB")
        else:
            print("\n❌ 合并失败")
            sys.exit(1)
    
    finally:
        # 清理临时文件（可选）
        print("\n🧹 清理临时文件...")
        if os.path.exists(temp_process_dir):
            for file in os.listdir(temp_process_dir):
                file_path = os.path.join(temp_process_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            os.rmdir(temp_process_dir)
            print("临时文件已清理")

if __name__ == "__main__":
    main()
