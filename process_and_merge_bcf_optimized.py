import sys
import os
import glob
import time

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
        
        # 使用更高效的方式处理文件
        chunk_size = 1048576  # 1MB chunks (更大的块提高I/O效率)
        min_text_length = 10  # 最小文本长度，视为元数据
        
        start_time = time.time()
        bytes_processed = 0
        bytes_written = 0
        
        with open(input_path, 'rb') as infile, open(output_path, 'wb') as outfile:
            buffer = b''
            
            while True:
                # 读取下一个块
                chunk = infile.read(chunk_size)
                if not chunk:
                    break
                
                bytes_processed += len(chunk)
                
                # 计算进度并显示
                progress = bytes_processed / file_size * 100
                if progress % 10 < 2:  # 每10%显示一次进度
                    print(f"  处理进度: {progress:.1f}% ({bytes_processed / (1024*1024):.1f} MB/{file_size / (1024*1024):.1f} MB)")
                
                # 添加到缓冲区
                buffer += chunk
                
                # 处理缓冲区
                pos = 0
                buffer_len = len(buffer)
                
                while pos < buffer_len:
                    # 查找文本序列的开始
                    while pos < buffer_len and not (32 <= buffer[pos] <= 126 or buffer[pos] in b'\n\r\t'):
                        pos += 1
                    
                    if pos >= buffer_len:
                        break
                    
                    # 查找文本序列的结束
                    text_start = pos
                    while pos < buffer_len and (32 <= buffer[pos] <= 126 or buffer[pos] in b'\n\r\t'):
                        pos += 1
                    
                    # 检查文本长度
                    if pos - text_start >= min_text_length:
                        # 这是文本（保留）
                        text_data = buffer[text_start:pos]
                        outfile.write(text_data)
                        bytes_written += len(text_data)
                    
                    # 优化：查找下一个文本的开始，跳过中间的二进制数据
                    # 不使用逐字节检查，而是使用更高效的方法
                    while pos < buffer_len and not (32 <= buffer[pos] <= 126 or buffer[pos] in b'\n\r\t'):
                        pos += 1
                
                # 保留剩余缓冲区内容用于下一次迭代
                buffer = buffer[pos:]
            
            # 处理剩余数据
            if buffer:
                # 检查剩余缓冲区是否为文本
                text_count = sum(1 for b in buffer if 32 <= b <= 126 or b in b'\n\r\t')
                if text_count / len(buffer) > 0.8:  # 如果80%以上是文本，保留
                    outfile.write(buffer)
                    bytes_written += len(buffer)
        
        # 验证结果
        processing_time = time.time() - start_time
        new_size = os.path.getsize(output_path)
        print(f"处理后大小: {new_size / (1024*1024):.2f} MB")
        print(f"压缩比例: {((file_size - new_size) / file_size * 100):.2f}%")
        print(f"处理时间: {processing_time:.2f} 秒")
        print(f"处理速度: {(bytes_processed / (1024*1024)) / processing_time:.2f} MB/秒")
        
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
    total_processing_time = 0
    
    # 处理每个文件块
    for i, chunk_file in enumerate(chunk_files, 1):
        print(f"\n=== 处理块 {i}/{len(chunk_files)} ===")
        
        # 构建输出文件名
        base_name = os.path.basename(chunk_file)
        output_file = os.path.join(output_dir, f"processed_{base_name}")
        
        # 处理文件块
        start_time = time.time()
        if process_bcf_chunk(chunk_file, output_file):
            processed_files.append(output_file)
            total_processing_time += time.time() - start_time
        
        print(f"累计处理时间: {total_processing_time:.2f} 秒")
        print(f"预计剩余时间: {total_processing_time / i * (len(chunk_files) - i):.2f} 秒")
    
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
        total_processing_time = 0
        
        with open(output_path, 'wb') as outfile:
            for i, input_file in enumerate(input_files, 1):
                file_size = os.path.getsize(input_file)
                total_size += file_size
                
                print(f"合并文件 {i}/{len(input_files)}: {os.path.basename(input_file)} ({file_size / (1024*1024):.2f} MB)")
                
                # 分块读取并写入，避免内存问题
                start_time = time.time()
                with open(input_file, 'rb') as infile:
                    while True:
                        chunk = infile.read(1048576)  # 1MB chunks
                        if not chunk:
                            break
                        outfile.write(chunk)
                
                file_time = time.time() - start_time
                total_processing_time += file_time
                print(f"  处理时间: {file_time:.2f} 秒")
                print(f"  预计剩余时间: {total_processing_time / i * (len(input_files) - i):.2f} 秒")
        
        print(f"\n✅ 合并完成！")
        print(f"输出文件: {output_path}")
        print(f"总大小: {total_size / (1024*1024):.2f} MB")
        print(f"总合并时间: {total_processing_time:.2f} 秒")
        
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
        print("用法: python process_and_merge_bcf_optimized.py input_chunk_dir output_merged_file.bcf")
        print("示例: python process_and_merge_bcf_optimized.py data/SEM/split_parts data/SEM/1_metadata_only.bcf")
        sys.exit(1)
    
    input_chunk_dir = sys.argv[1]
    output_merged_file = sys.argv[2]
    
    print("="*60)
    print("BCF文件处理与合并工具 (优化版)")
    print("功能：删除像素内容，保留元数据和样本扫描信息")
    print("="*60)
    
    # 创建临时处理目录
    temp_process_dir = os.path.join(os.path.dirname(output_merged_file), "temp_processed_chunks")
    os.makedirs(temp_process_dir, exist_ok=True)
    
    try:
        overall_start_time = time.time()
        
        # 第一步：处理所有文件块
        print("\n📋 第一步：处理所有文件块，删除像素内容...")
        processed_files = process_all_chunks(input_chunk_dir, temp_process_dir)
        
        if not processed_files:
            print("❌ 没有成功处理的文件块，任务中止")
            sys.exit(1)
        
        print(f"\n📊 处理统计：")
        print(f"- 总文件块数: {len(glob.glob(os.path.join(input_chunk_dir, '*.bcf')))}")
        print(f"- 成功处理: {len(processed_files)}")
        
        # 第二步：合并处理后的文件块
        print("\n🔄 第二步：合并处理后的文件块...")
        if merge_files(processed_files, output_merged_file):
            overall_time = time.time() - overall_start_time
            print("\n🎉 任务完成！")
            print(f"\n📁 最终生成的元数据文件：")
            print(f"- {output_merged_file}")
            print(f"- 大小: {os.path.getsize(output_merged_file) / (1024*1024):.2f} MB")
            print(f"- 总耗时: {overall_time:.2f} 秒")
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