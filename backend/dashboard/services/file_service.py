import os
import hashlib
from dashboard.models import File

class FileService:
    def scan_filesystem(self, start_dir='/'):
        for dirpath, dirnames, filenames in os.walk(start_dir):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                checksum = self.calculate_checksum(file_path)
                self.update_file_info(file_path, checksum)

    def calculate_checksum(self, file_path):
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as afile:
            buf = afile.read()
            hasher.update(buf)
        return hasher.hexdigest()

    def update_file_info(self, file_path, checksum):
        file, created = File.objects.get_or_create(path=file_path, defaults={'checksum': checksum})
        if not created and file.checksum != checksum:
            file.checksum = checksum
            file.save()
        duplicates = File.objects.filter(checksum=checksum).count()
        if duplicates > 1:
            File.objects.filter(checksum=checksum).update(duplicate_count=duplicates-1)
