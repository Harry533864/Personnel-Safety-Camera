from ruamel.yaml import YAML
from typing import List
from ruamel.yaml.comments import CommentedSeq, CommentedMap

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

def _to_polygon_format(points):
    """将 [[x,y], ...] 转换为 ruamel.yaml 要求的格式：外层 block，内层 flow"""
    outer = CommentedSeq()
    for pt in points:
        inner = CommentedSeq(pt)
        inner.fa.set_flow_style()   # 让 [x, y] 写在一行
        outer.append(inner)
    
    # 外层不设置 flow_style（默认 block，每个元素一行）
    return outer

def update_roi_polygon(
    file_path: str,
    roi_id: str,
    new_polygon: List[List[float]],
    create_roi_if_missing: bool = False
) -> bool:
    yaml = YAML()
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    # 读取文件
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.load(f)
    except FileNotFoundError:
        print(f"错误：文件 {file_path} 不存在")
        return False
    except Exception as e:
        print(f"读取文件失败：{e}")
        return False

    if data is None:
        data = {}

    try:
        # 获取或创建 model 节点
        model = data.get('model')
        if model is None:
            if create_roi_if_missing:
                data['model'] = {'rois': []}
                model = data['model']
            else:
                print("错误：配置中没有 'model' 节点")
                return False

        # 获取或创建 rois 列表
        rois = model.get('rois')
        if rois is None:
            if create_roi_if_missing:
                rois = []
                model['rois'] = rois
            else:
                print("错误：model 中没有 'rois' 列表")
                return False

        # 在 rois 列表中查找匹配的 roi_id
        target_roi = None
        for roi in rois:
            if isinstance(roi, dict) and roi.get('roi_id') == roi_id:
                target_roi = roi
                break

        if target_roi is None:
            if not create_roi_if_missing:
                print(f"错误：未找到 roi_id='{roi_id}'，且 create_roi_if_missing=False")
                return False
            
            # 创建新 ROI
            new_roi = {
                'roi_id': roi_id,
                'name': '新区域',
                'enabled': True,
                'roi_type': 'forbidden_zone',
                'judge_method': 'foot_point',
                'coordinate_mode': 'normalized',
                'polygon': _to_polygon_format(new_polygon),
                'overlap_thres': 0.2
            }
            rois.append(new_roi)
            print(f"已创建新 ROI: {roi_id}")
        else:
            # 修改现有 polygon
            target_roi['polygon'] = _to_polygon_format(new_polygon)
            print(f"已更新 ROI: {roi_id}")

        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f)
        return True

    except Exception as e:
        print(f"更新失败：{e}")
        return False

def update_yaml_detect_state(new_value, file_path="AIConfig.yaml", key_path=None):
    if key_path is None:
        key_path = ['model', 'detect_enable']
    
    state = update_yaml_param(file_path, key_path, new_value)
    if not state:
        raise ValueError("更新检测状态失败..")

def update_yaml_model_name(new_value, file_path="AIConfig.yaml", key_path=None):
    if key_path is None:
        key_path = ['model', 'model_name']
    
    state = update_yaml_param(file_path, key_path, new_value)
    if not state:
        raise ValueError("更新模型失败..")

def update_yaml_conf(new_value, file_path="AIConfig.yaml", key_path=None):
    if key_path is None:
        key_path = ['model', 'conf_thres']
    
    state = update_yaml_param(file_path, key_path, new_value)
    if not state:
        raise ValueError("更新置信度失败..")

def update_yaml_iou(new_value, file_path="AIConfig.yaml", key_path=None):
    if key_path is None:
        key_path = ['model', 'iou_thres']
    
    state = update_yaml_param(file_path, key_path, new_value)
    if not state:
        raise ValueError("更新IoU失败..")

def update_yaml_exposure(new_value, file_path="xx.yaml", key_path=None):
    """
    更新曝光值 (LiveStreamLayer.exposure)
    """
    if key_path is None:
        key_path = ['LiveStreamLayer', 'exposure']
    return update_yaml_param(file_path, key_path, new_value)


def update_yaml_resolution(target, new_height, new_width, file_path="xx.yaml"):
    """
    更新指定目标（HIGH 或 LOW）的分辨率
    target: 'HIGH' 或 'LOW'（不区分大小写，内部会转为大写）
    new_height: 新的高度值
    new_width:  新的宽度值
    """
    target_upper = target.upper()
    # 分别更新 width 和 height
    ok1 = update_yaml_param(file_path, ['LiveStreamLayer', target_upper, 'width'], new_width)
    ok2 = update_yaml_param(file_path, ['LiveStreamLayer', target_upper, 'height'], new_height)
    return ok1 and ok2

def update_yaml_fps(target, new_value, file_path="xx.yaml"):
    """
    更新指定目标（HIGH 或 LOW）的帧率
    target: 'HIGH' 或 'LOW'（不区分大小写，内部会转为大写）
    """
    target_upper = target.upper()
    return update_yaml_param(file_path, ['LiveStreamLayer', target_upper, 'fps'], new_value)

def rect_to_polygon(rect, h, w, digits=4):
    """
    将未归一化的矩形（左上角，右下角）转换为归一化的四边形四点表示。

    参数:
        rect: tuple ((x1, y1), (x2, y2))，未归一化坐标，可以是 int 或 float。
        h: 原始图像高度。
        w: 原始图像宽度。
        digits: 转换后保留的小数位

    返回:
        list: 四个点的列表，每个点为 [x_norm, y_norm]，归一化坐标（0~1）。
              顺序：左上 → 右上 → 右下 → 左下。
    """
    (x1, y1), (x2, y2) = rect
    x_left = min(x1, x2)
    x_right = max(x1, x2)
    y_top = min(y1, y2)
    y_bottom = max(y1, y2)

    # 归一化并保留两位小数
    x_left_norm = round(x_left / w, digits)
    x_right_norm = round(x_right / w, digits)
    y_top_norm = round(y_top / h, digits)
    y_bottom_norm = round(y_bottom / h, digits)

    # 按顺时针顺序：左上、右上、右下、左下
    polygon = [
        [x_left_norm, y_top_norm],     # 左上
        [x_right_norm, y_top_norm],    # 右上
        [x_right_norm, y_bottom_norm], # 右下
        [x_left_norm, y_bottom_norm]   # 左下
    ]

    return polygon


def polygon_to_rect(polygon, h, w):
    """
    将归一化的四边形四点表示转换为未归一化的外接矩形（左上角，右下角）。

    参数:
        polygon: list of list，四个点的列表，每个点为 [x_norm, y_norm]（0~1）。
        h: 原始图像高度。
        w: 原始图像宽度。

    返回:
        tuple: ((x1, y1), (x2, y2))，未归一化坐标。
               注意：如果四边形不是轴对齐矩形，此处返回其轴对齐包围盒。
    """
    # 提取归一化的 x, y 坐标
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]

    x_min_norm = min(xs)
    x_max_norm = max(xs)
    y_min_norm = min(ys)
    y_max_norm = max(ys)

    # 反归一化并四舍五入取整
    x1 = int(round(x_min_norm * w))
    y1 = int(round(y_min_norm * h))
    x2 = int(round(x_max_norm * w))
    y2 = int(round(y_max_norm * h))

    return ((x1, y1), (x2, y2))


if __name__ == '__main__':
    pass

    # config = "AIConfig.yaml"
    # data = read_yaml(config)
    # print(data)

    # updates = {("DetectionLayer", "model", "base"): "test"}
    # update_yaml_multi(config, updates)

    # data = read_yaml(config)
    # print(data)

    # 假设原始图像尺寸 1920x1080
    h, w = 1080, 1920

    # 1. 已知未归一化矩形：左上角 (200, 100)，右下角 (1500, 800)
    rect = ((200, 100), (1500, 800))
    polygon = rect_to_polygon(rect, h, w)
    print("转换后的四点（归一化）:")
    for pt in polygon:
        print(f"  [{pt[0]:.4f}, {pt[1]:.4f}]")

    # 2. 从四点（归一化）还原回未归一化矩形（外接矩形）
    recovered_rect = polygon_to_rect(polygon, h, w)
    print("\n还原的未归一化矩形:")
    print(f"  左上角: {recovered_rect[0]}")
    print(f"  右下角: {recovered_rect[1]}")