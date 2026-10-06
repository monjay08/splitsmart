from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .services import CSVError, analyze_csv

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


@api_view(["GET"])
def health(request):
    return Response({"status": "ok", "endpoint": "POST /api/analyze/ (multipart, field 'file')"})


class AnalyzeView(APIView):
    """Thin view: validate the upload, call the service, return JSON."""

    parser_classes = [MultiPartParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "No file uploaded. Send a CSV in the form field 'file'."}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith(".csv"):
            return Response({"error": "Wrong file type. Please upload a .csv file."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > MAX_UPLOAD_BYTES:
            return Response({"error": "File is too large (max 2 MB)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(analyze_csv(upload.read()))
        except CSVError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
