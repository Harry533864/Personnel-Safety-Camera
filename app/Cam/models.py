from pathlib import Path
from ruamel.yaml import YAML

ROOT = Path(__file__).parent.parent

class Model:
    def __init__(self, config=f"{ROOT}/AIConfig.yaml"):
        pass

    def inference(self, frame):
        """
        输入：图像（np.ndarray）、检测区域（从AIConfig.yaml读取）、置信度、IoU
        输出：图像 + 检测区域框 + 检测结果框
        """
        pass


if __name__ == '__main__':
    pass