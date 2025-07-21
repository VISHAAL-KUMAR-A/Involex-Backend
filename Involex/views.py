from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import openai
import time
from .serializers import EmailSummarySerializer, EmailSummaryResponseSerializer


class EmailSummaryAPIView(APIView):
    """
    API View to summarize emails using OpenAI GPT model.
    Specifically designed for lawyers to create billable entries.
    """

    def post(self, request):
        start_time = time.time()

        # Validate input data
        serializer = EmailSummarySerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid input data", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = serializer.validated_data
        email_content = validated_data['email_content']
        sender_email = validated_data.get('sender_email', '')
        recipient_email = validated_data.get('recipient_email', '')
        subject = validated_data.get('subject', '')

        try:
            # Initialize OpenAI client
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

            # Create the prompt for legal email summarization
            prompt = self._create_legal_summary_prompt(
                email_content, sender_email, recipient_email, subject
            )

            # Call OpenAI API
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a legal assistant helping lawyers create concise, professional summaries of client communications for billing purposes."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=500,
                temperature=0.3
            )

            summary = response.choices[0].message.content.strip()

            # Calculate word counts
            original_word_count = len(email_content.split())
            summary_word_count = len(summary.split())

            # Create billable description
            billable_description = self._create_billable_description(
                summary, sender_email, recipient_email, subject
            )

            processing_time = time.time() - start_time

            # Prepare response
            response_data = {
                "summary": summary,
                "word_count_original": original_word_count,
                "word_count_summary": summary_word_count,
                "billable_description": billable_description,
                "processing_time": round(processing_time, 2)
            }

            # Validate response data
            response_serializer = EmailSummaryResponseSerializer(
                data=response_data)
            if response_serializer.is_valid():
                return Response(response_serializer.data, status=status.HTTP_200_OK)
            else:
                return Response(
                    {"error": "Response validation failed",
                        "details": response_serializer.errors},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except openai.OpenAIError as e:
            return Response(
                {"error": "OpenAI API error", "details": str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            return Response(
                {"error": "Internal server error", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _create_legal_summary_prompt(self, email_content, sender_email, recipient_email, subject):
        """Create a specialized prompt for legal email summarization"""
        prompt = f"""
Please summarize the following email for legal billing purposes. The summary should be:
1. Professional and concise
2. Include key legal matters discussed
3. Mention any action items or next steps
4. Be suitable for client billing records
5. Focus on the substantive legal content

Email Details:
Subject: {subject}
From: {sender_email}
To: {recipient_email}

Email Content:
{email_content}

Please provide a concise professional summary (2-3 sentences) that captures the essential legal communication for billing purposes.
"""
        return prompt

    def _create_billable_description(self, summary, sender_email, recipient_email, subject):
        """Create a formatted billable entry description"""
        if sender_email and recipient_email:
            parties = f"Email correspondence with {recipient_email if sender_email else 'client'}"
        else:
            parties = "Email correspondence"

        subject_text = f" regarding {subject}" if subject else ""

        billable_description = f"{parties}{subject_text}. {summary}"

        return billable_description

    def get(self, request):
        """GET method to provide API documentation"""
        return Response({
            "message": "Email Summary API for Legal Professionals",
            "description": "POST email content to receive AI-powered summaries for billing purposes",
            "endpoint": "/api/summarize-email/",
            "method": "POST",
            "required_fields": ["email_content"],
            "optional_fields": ["sender_email", "recipient_email", "subject"],
            "example_request": {
                "email_content": "Dear Client, I have reviewed your contract...",
                "sender_email": "lawyer@lawfirm.com",
                "recipient_email": "client@company.com",
                "subject": "Contract Review Update"
            }
        })
