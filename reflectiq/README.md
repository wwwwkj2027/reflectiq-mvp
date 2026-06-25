# ReflectIQ

ReflectIQ is a Replit-based MVP for the NYU Emerging Technologies course. It converts student reflections into anonymous, aggregated faculty-facing learning intelligence.

## Live Demo

Replit Demo: https://reflectiq-mvp.replit.app

## Project Purpose

ReflectIQ helps faculty identify class-level learning patterns from student reflections. It is not a grading tool, ranking tool, or surveillance system.

## Main Features

- Student three-step Socratic reflection form
- AI-generated follow-up question
- Learning signal classification
- Anonymous clustering and aggregation
- Faculty dashboard
- Completion tracking page
- Governance page
- API setup page

## Project Structure

reflectiq/
- app.py: Flask backend
- requirements.txt: Python dependencies
- data/: course topics and sample data
- templates/: HTML pages
- static/: CSS and JavaScript files

## How to Run Locally

1. Clone the repository
2. Go into the project folder
3. Install dependencies:

pip install -r reflectiq/requirements.txt

4. Run the app:

python reflectiq/app.py

5. Open the local URL shown in the terminal.

## API Key Setup

The MVP can use an OpenAI API key for AI-generated follow-up questions and signal classification.

For Replit:
- Add `OPENAI_API_KEY` in Replit Secrets, or
- Use the API Setup page in the app for demo testing.

Do not upload API keys to GitHub.

## Sample Dataset

The project includes simulated student reflections connected to Emerging Technologies course topics and learning objectives. These are demo records only. No real student data is used.

## Governance Note

ReflectIQ separates completion tracking from learning analysis.

- Completion tracking shows who submitted and when.
- Learning analysis is anonymized.
- Dashboard results are aggregated.
- No grading.
- No ranking.
- No individual student surveillance.
- Faculty decision remains final.

## Team

Team 3  
Yubo Liu, Kangjie Gao, Ruiqi Han  
MASY1-GC1800 Emerging Technologies
