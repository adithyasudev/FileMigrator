from rclone import list_remotes
from app_paths import get_rclone_executable

print("RCLONE PATH:")
print(get_rclone_executable())

print()

print("REMOTES:")
print(list_remotes())

input("\nPress Enter to close...")