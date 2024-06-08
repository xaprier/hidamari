class Monitor:
    def __init__(self, name, width, height, x, y, primary, wallpaper=None):
        self.width = width
        self.height = height
        self.wallpaper = wallpaper
        self.primary = primary
        self.x = x
        self.y = y
        self.name = name

    def set_wallpaper(self, wallpaper):
        self.wallpaper = wallpaper

    def __str__(self):
        return f"Monitor(name={self.name}, x={self.x}, y={self.y}, width={self.width}, height={self.height}, primary={self.primary}, wallpaper={self.wallpaper})"
from screeninfo import get_monitors

class MonitorInfo:
    @staticmethod
    def get_unique_monitor_count():
        monitors = get_monitors()
        unique_names = set()

        for monitor in monitors:
            unique_names.add(monitor.name)

        return len(unique_names)

    @staticmethod
    def monitors():
        return get_monitors()

class Monitors:
    def __init__(self):
        self.monitors = [Monitor(monitor.name, monitor.width, monitor.height, monitor.x, monitor.y, monitor.is_primary) for monitor in MonitorInfo.monitors()]


    def get_monitor_by_index(self, index):
        if 0 <= index < len(self.monitors):
            return self.monitors[index]
        else:
            return None
    
    def get_monitors(self):
        return self.monitors
    
    def __str__(self):
        return "\n".join(str(monitor) for monitor in self.monitors)

# example
monitors = Monitors()
print(monitors)
# monitors = get_monitors()
# print(monitors)
# monitors = get_monitors()
# for monitor in monitors:
#     print(monitor.name)  # Bu, monitörlerin bağlı oldukları girişlerin isimlerini verecektir

