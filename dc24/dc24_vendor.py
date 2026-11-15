"""旧模块名兼容入口；实现位于独立 dc24-driver-vendor 发行包。"""

from dc24_driver_vendor import VendorConnection, VendorDriver

__all__ = ["VendorConnection", "VendorDriver"]
