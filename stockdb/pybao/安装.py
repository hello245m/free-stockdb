# install_path.py
import os
import sys
import site

def main():
    """
    将当前脚本所在的目录永久添加到 Python 的 sys.path 中。
    这是通过在 site-packages 目录中创建一个 .pth 文件来实现的。
    """
    # 1. 获取当前脚本所在的目录（项目根目录）
    project_root = os.path.dirname(os.path.abspath(__file__))
    project_name = os.path.basename(project_root)
    print(f"当前项目路径: {project_root}")

    # 2. 确定要写入 .pth 文件的 site-packages 目录
    # 优先使用用户级别的 site-packages，这样不需要管理员权限
    target_dir = site.USER_SITE
    if not target_dir or not os.path.isdir(target_dir):
        # 如果用户目录不存在或不可用，则使用系统级的 site-packages
        try:
            target_dir = site.getsitepackages()[0]
        except (AttributeError, IndexError):
            print("错误：无法找到 site-packages 目录。")
            sys.exit(1)

    print(f"目标 .pth 文件将创建于: {target_dir}")

    # 3. 定义 .pth 文件的完整路径
    pth_file_path = os.path.join(target_dir, f"{project_name}.pth")

    # 4. 检查路径是否已经存在于 .pth 文件中，避免重复添加
    path_already_exists = False
    if os.path.exists(pth_file_path):
        with open(pth_file_path, 'r') as f:
            existing_paths = f.read().splitlines()
            if project_root in existing_paths:
                path_already_exists = True
                print(f"路径已存在于 {pth_file_path} 中，无需重复添加。")

    # 5. 如果路径不存在，则追加到 .pth 文件中
    if not path_already_exists:
        try:
            with open(pth_file_path, 'a') as f:
                f.write(project_root + os.linesep) # os.linesep 确保跨平台换行符正确
            print(f"成功！项目路径已写入到: {pth_file_path}")
            print("请重启您的 Python 解释器或 IDE 以使更改生效。")
        except PermissionError:
            print(f"错误：权限不足，无法写入文件 {pth_file_path}")
            print("请尝试以管理员身份运行此脚本。")
        except Exception as e:
            print(f"发生未知错误: {e}")

if __name__ == "__main__":
    main()