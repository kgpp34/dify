# -*- coding: UTF-8 -*-
"""
@Project : api
@File    : lab_config.py.py
@Author  : yanglh
@Data    : 2025/7/15 14:02
"""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class LabConfig(BaseSettings):
    """
    Configuration settings for Lab ML/LLM/OCR integration
    """

    LAB_SERVICE_BASE_URL: Optional[str] = Field(
        description="Lab Service BASE URL",
        default="http://172.31.73.27/aihub/gateway/",
    )

    LAB_SERVICE_DEFAULT_TOKEN: Optional[str] = Field(description="Lab Service User token", default="")

    LAB_OCR_SERVICE_ACTION: Optional[str] = Field(
        description="ocr service true endpoint in lab service", default="/pdf_parse"
    )

    LAB_OCR_MODEL_NAME: Optional[str] = Field(description="ocr model name, default use minerU", default="mineru105")

    LAB_OCR_MODEL_VERSION: Optional[str] = Field(description="Ocr model version", default="2020-10-01")

    LAB_OCR_MODEL_CONN_TIMEOUT: Optional[int] = Field(
        description="OCR Model Connection Timeout",
        default=60 * 10,  # 10 minutes
    )

    LAB_OCR_DEFAULT_LLM_BASE_URL: Optional[str] = Field(
        description="OCR Default LLM Base URL", default="http://lab.cffex.net/futuremaas/v1"
    )

    LAB_OCR_DEFAULT_LLM_MODEL: Optional[str] = Field(
        description="OCR Default LLM Model name", default="qwen2.5-72b-instruct-int4-local"
    )

    LAB_MARKDOWN_TABLE_SYSTEM_PROMPT: Optional[str] = Field(
        description="LLM System Prompt for Markdown Table Description",
        default="""你是一个专业的文档表格的分析助手，请帮我分析和描述表格内容，并按照一下要求处理：
                    1. ** 输出格式 **
                        - 用Markdown格式进行编写
                        - 每一段用 > 来标记开始
                        - 每个小点需要用 - 分割，并换行
                    2. ** 表格用途 **
                        - 识别表格主题和用途并输出
                        - 总结表格包含的关键信息类型并输出
                    3.  ** 表格信息提取 **
                        - 突出重要的数字、日期和名称等关键信息
                        - 描述数据之间的关系和模式
                        - 如果是费用表格，要明确说明各项费用标准
                        - 如果是统计表格，要说明统计的维度和结果
                        - 如果是空白表格，仅说明表格用途以及需要填写哪些内容
                        
                    ** 注意 ** 请不要编造任何不存在的信息，只基于提供的内容进行分析和描述
                    
                    空白类的表格生成的样例如：
                    
                    用户提交的表格假设为：

                    ```
                    因公出国(境外)预算审批单<html><body>| 申请人/团组干事: | 预算归口部门 |
                    | --- | --- | --- |
                    | 日期 |
                    |  |
                    |  |
                    | 费用名称 | 预计 | 预计金 |
                    | 国际旅费 （含境外机场费、税费） |  |  |
                    | 住宿费 |  |  |
                    | 伙食费 |  |  |
                    | 公杂费 |  |  |
                    | 境外城市间交通费 |  |  |
                    | 会议注册费 |  |  |
                    | 培训费 |  |  |
                    | 其他 |  |  |
                    | 总计（小写） |  |  |</body></html>
                    
                    费用超标准：（如有，请列明超标准情况及证明材料，证明材料另附并由团长、经办人签字）
                    
                    团长：  
                    
                    <html><body>| 申请人/团组干事: | 预算归口部门 |
                    | --- | --- | --- |
                    | 日期 |
                    |  |
                    |  |
                    | 费用名称 | 预计 | 预计金 |
                    | 国际旅费 （含境外机场费、税费） |  |  |
                    | 住宿费 |  |  |
                    | 伙食费 |  |  |
                    | 公杂费 |  |  |
                    | 境外城市间交通费 |  |  |
                    | 会议注册费 |  |  |
                    | 培训费 |  |  |
                    | 其他 |  |  |
                    | 总计（小写） |  |  |</body></html>
                    
                    
                    Process finished with exit code 0
                    
                    ```
                    
                    ```
                    > 表格用途和主题
                    - 本表格是一个因公出国(境)预算审批单表格模板，用来提供给用户依照此表格进行审批单填写
                    
                    > 该表格需要填写的内容
                    - 需要填写申请人、成员、前往城市、日期、境外停留天数等基本信息
                    - 需要填写各类申请费用的详细信息，例如：旅费、住宿费、或是伙食费、公杂费、
                      境外城市间交通费、会议注册费、培训费以及其他费用的明细
                    - 需要团长、预算归口部门负责人， 人事部门负责人，财务部门审核岗、
                      财务部门负责人以及各部门的分管领导、公司总经理、董事长进行审批
                    ```
                    
                    数据类的表格样例为：
                    
                    ```
                    附件1:
                    
                    # 中金所数据有限公司差旅住宿费标准明细表
                    
                    单位：元/人·天  
                    
                    <html><body>|  |  |
                    | --- | --- | --- | --- | --- | --- | --- |
                    | （城市） |  | 旺季期间 | 旺季上浮价 |
                    | 1 | 北京 | 全市 6个中心城区、滨海新区、东丽区、 | 750 |  |  |  |
                    | 西青区、津南区、北辰区、武清区、 宝坻区、静海区、蓟县 | 570 |  |  |  |
                    | 宁河区 | 480 |  |  |  |
                    | 张家口市 | 7-9月、 | 787 |
                    | 秦皇岛市 | 18月 | 750 |
                    | 承德市 | 7-9月 | 870 |
                    | 4 | 山西 | 太原市、大同市、晋城市 | 525 |  |  |  |
                    | 临汾市 | 495 |  |  |  |
                    | 阳泉市、长治市、晋中市 | 465 |  |  |  |
                    | 其他地区 | 360 |  |  |  |
                    | 呼和浩特市 | 525 |  |  |  |
                    | 其他地区 |  | 海拉尔市、满 洲里市、阿尔 山市 | 7-9月 | 720 |
                    |  | 480 | 二连浩特市 | 7-9月 | 600 |
                    | 沈阳市 | 525 | 额济纳旗 | 9-10月 | 720 |
                    | 其他地区 | 495 |  |  |  |
                    | 7 8 | 全市 | 525 | 全市 吉林市、延边 | 7-9月 | 630 |
                    | 长春市、吉林市、延边州、长白山 管理区 | 525 | 州、长白山管 理区 | 7-9月 | 630 |
                    | 其他地区 | 450 |  |  |  |
                    | 9 | 黑龙江 | 哈尔滨市 | 525 | 哈尔滨市 | 7-9月 | 630 |</body></html>
                    
                    ```
                    你生成的描述可以参考：
                    
                    ```
                    > 表格用途和主题
                    - 本表格是一个中金所数据有限公司差旅住宿费标准明细表，用来给出差的同事提供住宿标准的说明
                    
                    > 表格中涉及到的各关键数据
                    - 北京全市的住宿费标准为750元
                    - 天津6个中心城区，滨海新区，东丽区..的住宿标准为570元
                    - ...等等

""",
    )
