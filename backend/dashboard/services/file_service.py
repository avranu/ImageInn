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
        duplicates = File.objects.filter(checksum=checksum)
        if duplicates.count() > 1:
            file.duplicates.set(duplicates.exclude(id=file.id))
            file.duplicate_count = duplicates.count() - 1
            file.save()

    def checksum_changed(self, file):
        return file.checksum != self.calculate_checksum(file.path)

    def compare_checksums(self, file1, file2):
        return file1.checksum == file2.checksum

    def calculate_analytics(self):
        total_files = File.objects.count()
        total_duplicates = sum(file.duplicate_count for file in File.objects.all())
        total_unique_files = total_files - total_duplicates
        return {'total_files': total_files, 'total_duplicates': total_duplicates, 'total_unique_files': total_unique_files}

    def detect_corruption(self, file):
        return not file.exists() or self.checksum_changed(file)
from rest_framework import serializers
from dashboard.models import File

class FileSerializer(serializers.ModelSerializer):
    class Meta:
        model = File
        fields = ['path', 'checksum', 'duplicate_count', 'duplicates']

from rest_framework import viewsets

class FileViewSet(viewsets.ModelViewSet):
    queryset = File.objects.all()
    serializer_class = FileSerializer
