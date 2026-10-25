import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
import io
import pypdf

import syllabus
from app import app, extract_chunks_from_pdf_stream, JOBS, ADMIN_PASSWORD
from cloud_vector_store import CloudVectorStore

class Phase2Tests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_syllabus_and_namespace(self):
        # 1. CA Foundation
        self.assertIn("Accounting", syllabus.SYLLABUS["CA"]["Foundation"])
        self.assertIn("Business Laws", syllabus.SYLLABUS["CA"]["Foundation"])
        self.assertEqual(syllabus.namespace("CA", "Foundation"), "ca-foundation")

        # 2. CA Inter
        self.assertIn("Taxation", syllabus.SYLLABUS["CA"]["Inter"])
        self.assertIn("Corporate and Other Laws", syllabus.SYLLABUS["CA"]["Inter"])
        self.assertEqual(syllabus.namespace("CA", "Inter"), "ca-inter")

        # 3. CA Final
        self.assertIn("Financial Reporting", syllabus.SYLLABUS["CA"]["Final"])
        self.assertIn("Direct Tax Laws and International Taxation", syllabus.SYLLABUS["CA"]["Final"])
        self.assertEqual(syllabus.namespace("CA", "Final"), "ca-final")

        # 4. Validation
        self.assertTrue(syllabus.is_valid_course_level("CA", "Foundation"))
        self.assertTrue(syllabus.is_valid_course_level("CA", "Inter"))
        self.assertTrue(syllabus.is_valid_course_level("CA", "Final"))
        self.assertFalse(syllabus.is_valid_course_level("CA", "NonExistent"))

        # 5. CS and CMA placeholders exist
        self.assertIn("CS", syllabus.SYLLABUS)
        self.assertIn("CMA", syllabus.SYLLABUS)

    def test_syllabus_api_endpoint(self):
        res = self.client.get("/api/syllabus")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("syllabus", data)
        self.assertIn("CA", data["syllabus"])

    def test_chunking_with_context_prefix_and_ocr(self):
        # Create an in-memory PDF with 2 pages:
        # Page 1: normal text (> 40 chars)
        # Page 2: empty (simulating scanned image page)
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.add_blank_page(width=72, height=72)
        
        pdf_stream = io.BytesIO()
        writer.write(pdf_stream)
        pdf_stream.seek(0)

        # Mock pypdf reader pages text extraction
        with patch("pypdf.PdfReader") as mock_reader_cls:
            mock_reader = mock_reader_cls.return_value
            mock_page1 = unittest.mock.MagicMock()
            # 60 words for page 1
            mock_page1.extract_text.return_value = "Section 115BAC provides concessional tax rates for individuals and HUF. " * 5
            mock_page2 = unittest.mock.MagicMock()
            mock_page2.extract_text.return_value = "" # Scanned page

            mock_reader.pages = [mock_page1, mock_page2]

            total_pages, chunks, needs_ocr = extract_chunks_from_pdf_stream(
                pdf_stream,
                doc_name="Tax_Notes.pdf",
                subject="Taxation",
                course="CA",
                level="Inter"
            )

            self.assertEqual(total_pages, 2)
            self.assertTrue(needs_ocr) # Scanned page detected!
            self.assertGreaterEqual(len(chunks), 1)

            # Check context prefix
            first_chunk = chunks[0]
            self.assertIn("[Taxation | Tax_Notes.pdf | Page 1]", first_chunk["content"])
            self.assertEqual(first_chunk["course"], "CA")
            self.assertEqual(first_chunk["level"], "Inter")
            self.assertEqual(first_chunk["subject"], "Taxation")

    def test_cloud_vector_store_namespace_and_task_type(self):
        cvs = CloudVectorStore(gemini_api_key="test_key", pinecone_api_key="test_key")

        # Test upsert_chunks payload structure
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"upsertedCount": 1}
        mock_post = AsyncMock(return_value=mock_resp)

        chunks = [{
            "id": "c1",
            "course": "CA",
            "level": "Inter",
            "subject": "Taxation",
            "doc_name": "tax.pdf",
            "section": "Page 1",
            "topic": "Taxation",
            "content": "[Taxation | tax.pdf | Page 1]\nSection 115BAC text"
        }]

        with patch("cloud_vector_store.httpx.AsyncClient.post", mock_post):
            # Mock embed_batch
            with patch.object(cvs, "embed_batch", new_callable=AsyncMock, return_value=[[0.1] * 768]):
                import asyncio
                res = asyncio.run(cvs.upsert_chunks(chunks, namespace="ca-inter"))
                self.assertEqual(res.get("upsertedCount"), 1)
                
                # Check that namespace was passed in Pinecone payload
                call_args = mock_post.call_args
                posted_json = call_args.kwargs.get("json", {})
                self.assertEqual(posted_json.get("namespace"), "ca-inter")
                vectors = posted_json.get("vectors", [])
                self.assertEqual(len(vectors), 1)
                self.assertEqual(vectors[0]["metadata"]["course"], "CA")
                self.assertEqual(vectors[0]["metadata"]["level"], "Inter")

    def test_admin_upload_background_job_and_validation(self):
        # 1. Invalid course/level should reject with 400
        pdf_file = io.BytesIO(b"%PDF-1.4 test")
        res_invalid = self.client.post(
            "/api/admin/upload-cloud-pdf",
            headers={"X-Admin-Key": ADMIN_PASSWORD},
            data={"course": "InvalidCourse", "level": "InvalidLevel", "subject": "Law"},
            files={"file": ("test.pdf", pdf_file, "application/pdf")}
        )
        self.assertEqual(res_invalid.status_code, 400)
        self.assertIn("Invalid course/level", res_invalid.json().get("detail", ""))

        # 2. Valid course/level starts background job and returns immediately with job_id
        pdf_file.seek(0)
        with patch("app.cloud_store.upsert_chunks", new_callable=AsyncMock, return_value={"upsertedCount": 1}), \
             patch("app.extract_chunks_from_pdf_stream", return_value=(1, [{"id": "c1", "content": "text"}], False)):
            res_valid = self.client.post(
                "/api/admin/upload-cloud-pdf",
                headers={"X-Admin-Key": ADMIN_PASSWORD},
                data={"course": "CA", "level": "Inter", "subject": "Taxation"},
                files={"file": ("valid_test.pdf", pdf_file, "application/pdf")}
            )
            self.assertEqual(res_valid.status_code, 200)
            data = res_valid.json()
            self.assertTrue(data.get("success"))
            self.assertIn("job_id", data)
            self.assertEqual(data.get("namespace"), "ca-inter")

            job_id = data["job_id"]
            # 3. Check GET /api/admin/jobs/{job_id}
            job_res = self.client.get(f"/api/admin/jobs/{job_id}", headers={"X-Admin-Key": ADMIN_PASSWORD})
            self.assertEqual(job_res.status_code, 200)
            job_data = job_res.json()
            self.assertEqual(job_data.get("id"), job_id)
            self.assertEqual(job_data.get("course"), "CA")
            self.assertEqual(job_data.get("level"), "Inter")

if __name__ == "__main__":
    unittest.main()
