from ruamel.yaml import YAML

def read_yaml(file_path):
    """
    读取 YAML 文件并返回解析后的 Python 对象。
    保留原始格式（注释、缩进等）仅在写入时有用，读取后是普通数据。
    
    Args:
        file_path (str): YAML 文件路径
    
    Returns:
        dict/list: 解析后的数据，文件不存在或解析错误时返回 None
    """
    yaml = YAML()
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.load(f)
            return data
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return None
    except Exception as e:
        print(f"读取 YAML 文件失败：{e}")
        return None

def update_yaml_param(file_path, key_path, new_value, create_missing=False):
    """
    修改 YAML 文件中某个键路径对应的值，保留原始格式和注释。
    
    Args:
        file_path (str): YAML 文件路径
        key_path (list): 键路径，例如 ['server', 'port']
        new_value (any): 新值
        create_missing (bool): 如果路径中的中间键不存在，是否自动创建（默认 False）
    
    Returns:
        bool: 修改成功返回 True，否则 False
    """
    yaml = YAML()
    yaml.width = 4096          # 避免长字符串自动换行

    # 保留字符串的原始引号风格
    # yaml.preserve_quotes = True
    
    # 1. 读取原文件
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.load(f)
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return False
    except Exception as e:
        print(f"读取文件失败：{e}")
        return False
    
    # 2. 按路径逐级访问/创建
    if data is None:
        data = {}  # 空文件视为空字典
    
    current = data
    for i, key in enumerate(key_path):
        if i == len(key_path) - 1:
            # 最后一个键：赋值
            current[key] = new_value
        else:
            # 中间键：获取或创建下一级
            if key not in current:
                if create_missing:
                    current[key] = {}
                else:
                    print(f"错误：路径 {' → '.join(key_path[:i+1])} 不存在，且未开启 create_missing")
                    return False
            current = current[key]
    
    # 3. 写回文件（格式、注释全部保留）
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f)
        return True
    except Exception as e:
        print(f"写入文件失败：{e}")
        return False


def update_yaml_multi(file_path, updates, create_missing=False):
    """
    一次性修改多个参数
    updates: 字典，格式为 { ("path", "to", "key"): new_value, ... }
    """
    yaml = YAML()
    yaml.width = 4096          # 避免长字符串自动换行

    with open(file_path, 'r', encoding='utf-8') as f:
        data = yaml.load(f)
    
    for key_path, new_value in updates.items():
        current = data
        for i, key in enumerate(key_path):
            if i == len(key_path) - 1:
                current[key] = new_value
            else:
                if key not in current and create_missing:
                    current[key] = {}
                current = current[key]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f)


if __name__ == '__main__':
    config = "AIConfig.yaml"
    data = read_yaml(config)
    print(data)

    updates = {("DetectionLayer", "model", "base"): "test"}
    update_yaml_multi(config, updates)

    data = read_yaml(config)
    print(data)