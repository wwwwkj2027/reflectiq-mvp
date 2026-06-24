import os
import json
import uuid
import sqlite3
import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, g
from openai import OpenAI

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "reflectiq-dev-secret")

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "reflections.db")
COURSES_PATH = os.path.join(os.path.dirname(__file__), "data", "courses.json")

# ─── Runtime API key (demo-only: stored in process memory, never written to disk) ─
_runtime_api_key: str | None = None


def get_openai_client() -> OpenAI:
    """Return an OpenAI client using the runtime key if set, else the env var."""
    key = _runtime_api_key or os.environ.get("OPENAI_API_KEY", "")
    return OpenAI(api_key=key if key else "unset")

# ─── Course data ──────────────────────────────────────────────────────────────
with open(COURSES_PATH) as f:
    COURSE_DATA = json.load(f)

TOPIC_MAP = {}
for course in COURSE_DATA["courses"]:
    for topic in course["topics"]:
        TOPIC_MAP[topic["id"]] = {
            "label": topic["label"],
            "objectives": topic["objectives"],
            "key_concepts": topic.get("key_concepts", []),
            "common_confusions": topic.get("common_confusions", []),
            "example_applications": topic.get("example_applications", []),
            "course_name": course["name"],
            "course_id": course["id"],
            "code": course.get("code", ""),
            "semester": course.get("semester", ""),
            "week": topic.get("week", ""),
        }

# ─── Learning signals ─────────────────────────────────────────────────────────
SIGNALS = [
    "comprehension",
    "surface_understanding",
    "definitional_gap",
    "applied_transfer_difficulty",
    "pacing_concern",
    "support_need",
]

SIGNAL_LABELS = {
    "comprehension": "Comprehension",
    "surface_understanding": "Surface Understanding",
    "definitional_gap": "Definitional Gap",
    "applied_transfer_difficulty": "Applied-Transfer Difficulty",
    "pacing_concern": "Pacing Concern",
    "support_need": "Support Need",
}

SIGNAL_CSS = {
    "comprehension": "comprehension",
    "surface_understanding": "surface",
    "definitional_gap": "definitional",
    "applied_transfer_difficulty": "applied",
    "pacing_concern": "pacing",
    "support_need": "support",
}

SIGNAL_DESCRIPTIONS = {
    "comprehension": "Student demonstrates solid grasp of the concept",
    "surface_understanding": "Student knows terms but lacks depth",
    "definitional_gap": "Key vocabulary or definitions are unclear",
    "applied_transfer_difficulty": "Struggles to apply concept to new contexts",
    "pacing_concern": "Reflection suggests the pace may be too fast or slow",
    "support_need": "Signals a need for additional resources or check-in",
}

CLUSTER_META = {
    "comprehension": {
        "cluster_theme": "Conceptual Mastery",
        "faculty_insight": (
            "Students in this cluster demonstrate clear, nuanced understanding "
            "and can articulate the concept in their own words with genuine depth."
        ),
        "recommended_action": (
            "Leverage these students as peer discussion anchors. Introduce stretch "
            "content, advanced application challenges, or leadership roles in group work."
        ),
    },
    "surface_understanding": {
        "cluster_theme": "Vocabulary Without Depth",
        "faculty_insight": (
            "Students recognize the terminology and surface-level facts but have not "
            "yet internalized the underlying mechanisms, trade-offs, or 'why it matters'."
        ),
        "recommended_action": (
            "Introduce case studies that force movement beyond definitions. Structured "
            "debate or Socratic dialogue can surface and challenge shallow assumptions."
        ),
    },
    "definitional_gap": {
        "cluster_theme": "Terminology Confusion",
        "faculty_insight": (
            "Core vocabulary appears unclear or conflated. Students may be confusing "
            "related but distinct concepts, or using terms interchangeably that are not."
        ),
        "recommended_action": (
            "Dedicate 10–15 minutes to a live vocabulary clarification activity. A "
            "concept-mapping exercise or glossary co-creation can help anchor definitions."
        ),
    },
    "applied_transfer_difficulty": {
        "cluster_theme": "Application Barrier",
        "faculty_insight": (
            "Students understand the concept in isolation but struggle to transfer it "
            "to novel business or technology scenarios they have not seen before."
        ),
        "recommended_action": (
            "Introduce scaffolded case applications with worked examples. Pair students "
            "to work through real-world analogies together before individual application tasks."
        ),
    },
    "pacing_concern": {
        "cluster_theme": "Pacing Friction",
        "faculty_insight": (
            "Reflections suggest the session moved too fast or too slow for a meaningful "
            "subset of students, creating engagement or comprehension gaps."
        ),
        "recommended_action": (
            "Run a quick anonymous pulse check. Consider chunking the next session "
            "differently or providing optional pre-reading or review materials."
        ),
    },
    "support_need": {
        "cluster_theme": "Active Support Required",
        "faculty_insight": (
            "A subset of students signal they need additional guidance, resources, "
            "or a direct check-in that goes beyond the regular class session."
        ),
        "recommended_action": (
            "Reach out via office hours or share targeted supplementary materials. "
            "Consider a structured study guide or optional review session for this topic."
        ),
    },
}

AGGREGATION_THRESHOLD = 3


# ─── Dummy / demo data ────────────────────────────────────────────────────────
DUMMY_REFLECTIONS = [
    # ── intro_origins ─── 5 reflections
    {
        "topic_id": "intro_origins",
        "topic_label": "Introduction: Origins of Technology & Life Cycle Stages",
        "q1": "I learned that technologies go through predictable life cycles — from the S-curve to the Gartner Hype Cycle — and that emergence is more about societal uptake than the invention itself.",
        "followup_q": "If technologies emerge through societal uptake, what would cause a technology to stall before reaching mainstream adoption?",
        "q2": "If a technology stalls it's usually because the market isn't ready or costs are too high. Like early VR — the tech existed but it didn't take off until prices dropped.",
        "q3": "I'd apply the S-curve to cloud computing adoption in healthcare. The regulatory environment slowed the curve, but once HIPAA-compliant solutions appeared the curve steepened quickly.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Students understand the technology life cycle but cannot apply it to a current technology",
        "faculty_insight": "Students can recite life cycle stages but struggle to map real technologies onto those frameworks with supporting evidence.",
        "recommended_action": "Use a live mapping exercise where students place 3 current technologies on the Hype Cycle and defend their placement with data.",
        "confidence": "high",
    },
    {
        "topic_id": "intro_origins",
        "topic_label": "Introduction: Origins of Technology & Life Cycle Stages",
        "q1": "The S-curve shows how adoption accelerates then plateaus. I think most technologies follow this but some like blockchain seem stuck even after years.",
        "followup_q": "Why might blockchain remain in early stages while AI has moved faster — what adoption conditions differ between them?",
        "q2": "AI has more obvious consumer applications like ChatGPT while blockchain needs developers to build things on top of it. The use cases aren't as immediate.",
        "q3": "I'd use the Gartner Hype Cycle to advise a fintech startup on when to integrate blockchain. Right now it seems like it's in the trough so maybe wait a bit.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Students understand the technology life cycle but cannot apply it to a current technology",
        "faculty_insight": "Students rely on intuition rather than framework criteria when positioning technologies on adoption curves.",
        "recommended_action": "Assign a structured framework application: students must cite adoption metrics and peer benchmarks to justify their placement.",
        "confidence": "medium",
    },
    {
        "topic_id": "intro_origins",
        "topic_label": "Introduction: Origins of Technology & Life Cycle Stages",
        "q1": "Technologies don't emerge from nowhere — they need the right conditions. The Hype Cycle was a new concept for me and the idea of a trough of disillusionment is counterintuitive.",
        "followup_q": "What separates technologies that recover from the trough of disillusionment from those that never reach the plateau of productivity?",
        "q2": "I think it depends on whether real business value can be proven. If companies can't show ROI during the trough they give up and the technology fades.",
        "q3": "Applying this to autonomous vehicles: they seem to be in the trough right now. Companies like Waymo are doing limited tests but mass adoption hasn't happened. The question is whether the business model will ever work.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Students understand the technology life cycle but cannot apply it to a current technology",
        "faculty_insight": "Students grasp the conceptual narrative of the Hype Cycle but struggle to identify objective signals for each stage.",
        "recommended_action": "Provide a rubric for stage identification: adoption rate, investment levels, press sentiment, and commercial deployments as stage indicators.",
        "confidence": "high",
    },
    {
        "topic_id": "intro_origins",
        "topic_label": "Introduction: Origins of Technology & Life Cycle Stages",
        "q1": "I think I understand the Hype Cycle — technologies get overhyped at first and then people realize the limits. The hype is basically like a bubble.",
        "followup_q": "Is the hype itself harmful, or does it serve a useful function in the adoption process?",
        "q2": "I think hype can be harmful because it sets unrealistic expectations. But it also attracts investment so maybe it's both helpful and harmful at the same time.",
        "q3": "For generative AI, companies are trying to use it for everything right now which might be the hype peak. I would use the S-curve to figure out when AI is actually ready for my industry.",
        "signal": "surface_understanding",
        "signal_label": "Surface Understanding",
        "cluster_theme": "Students confuse hype with real adoption readiness",
        "faculty_insight": "Students conflate hype cycles with market readiness signals, treating high media attention as an indicator of adoption maturity.",
        "recommended_action": "Show historical examples where peak hype diverged from actual adoption timelines — dot-com vs. actual e-commerce growth.",
        "confidence": "medium",
    },
    {
        "topic_id": "intro_origins",
        "topic_label": "Introduction: Origins of Technology & Life Cycle Stages",
        "q1": "The main takeaway was that emergence isn't just invention — it's when something becomes widely used. The Hype Cycle tracks sentiment more than actual adoption.",
        "followup_q": "If the Hype Cycle tracks sentiment and not adoption, what tool would you use to measure actual adoption readiness?",
        "q2": "I'm not sure what tool to use. Maybe market share data or usage statistics? I wasn't sure what specific frameworks exist for measuring actual adoption.",
        "q3": "I'd try to apply some kind of readiness assessment to decide if my company should adopt a new technology. The Hype Cycle isn't enough on its own — you need real data.",
        "signal": "surface_understanding",
        "signal_label": "Surface Understanding",
        "cluster_theme": "Students confuse hype with real adoption readiness",
        "faculty_insight": "Students recognize the limitation of hype-based assessment but lack specific tools to assess actual adoption readiness.",
        "recommended_action": "Introduce Technology Readiness Levels (TRLs) and adoption metrics as concrete alternatives to sentiment-based assessment.",
        "confidence": "medium",
    },

    # ── diffusion_innovation ─── 4 reflections
    {
        "topic_id": "diffusion_innovation",
        "topic_label": "Diffusion of Innovation",
        "q1": "Rogers' framework was eye-opening. The five adopter categories make sense — innovators take risks, laggards resist. The chasm concept between early adopters and early majority was the most useful part.",
        "followup_q": "If the chasm is the most critical barrier, what specific strategies have companies used to successfully cross it?",
        "q2": "Companies target a niche segment of the early majority, dominate that segment, then expand. I think Apple did this with the iPhone by targeting professionals before going mass-market.",
        "q3": "I'd apply chasm theory to a B2B SaaS product. Win one vertical completely — say healthcare — before expanding to other industries. The beachhead strategy from Geoffrey Moore's book.",
        "signal": "comprehension",
        "signal_label": "Comprehension",
        "cluster_theme": "Conceptual Mastery",
        "faculty_insight": "Student demonstrates solid grasp of chasm theory and can apply it to a real business context with appropriate specificity.",
        "recommended_action": "Invite this student to present their beachhead strategy analysis as a class discussion anchor in the next session.",
        "confidence": "high",
    },
    {
        "topic_id": "diffusion_innovation",
        "topic_label": "Diffusion of Innovation",
        "q1": "Diffusion of innovation is basically how ideas spread through society. The model shows different types of people who adopt technology at different speeds.",
        "followup_q": "You've described who adopts — but what factors determine whether a technology diffuses quickly or slowly?",
        "q2": "I think price matters a lot. And whether it's easy to use. If a technology is too complicated most people won't adopt it even if early adopters love it.",
        "q3": "For a new healthcare app, I'd focus on making it easy to use so the early majority would adopt it. Marketing to innovators first then expanding.",
        "signal": "definitional_gap",
        "signal_label": "Definitional Gap",
        "cluster_theme": "Students understand diffusion theory but cannot explain crossing the chasm",
        "faculty_insight": "Students describe adoption demographics but miss Rogers' five diffusion attributes (relative advantage, compatibility, complexity, trialability, observability).",
        "recommended_action": "Run a structured analysis using all five Rogers attributes applied to a current technology before the next class session.",
        "confidence": "high",
    },
    {
        "topic_id": "diffusion_innovation",
        "topic_label": "Diffusion of Innovation",
        "q1": "The S-curve and the diffusion curve seem to be the same thing to me. I learned about different types of adopters but the chasm part was confusing.",
        "followup_q": "The S-curve and diffusion curve describe related but different phenomena — can you articulate where they diverge?",
        "q2": "I'm not entirely sure where they differ. I think the S-curve is about overall market penetration while diffusion is more about the people who adopt? But I'm not confident in that distinction.",
        "q3": "I'd want to understand this better before applying it. For now I'd say a company launching a new product should think about who the early adopters are and try to target them.",
        "signal": "definitional_gap",
        "signal_label": "Definitional Gap",
        "cluster_theme": "Students understand diffusion theory but cannot explain crossing the chasm",
        "faculty_insight": "Students conflate the S-curve (cumulative adoption over time) with the diffusion bell curve (adopter segment distribution) — these are complementary but distinct models.",
        "recommended_action": "Show both curves overlaid on a single timeline with the same technology example. Ask students to annotate each with the framework it represents.",
        "confidence": "high",
    },
    {
        "topic_id": "diffusion_innovation",
        "topic_label": "Diffusion of Innovation",
        "q1": "Diffusion is about how and why new ideas spread. Rogers identified five adopter types. The chasm is when a technology has to cross from tech enthusiasts to mainstream users.",
        "followup_q": "What organizational changes does a company typically need to make to successfully cross from early adopters to early majority?",
        "q2": "I think companies need to change their messaging — early adopters love novelty while the early majority wants reliability and proof. The sales process probably changes too.",
        "q3": "For a company selling AI writing tools: pivot from marketing the innovation to marketing the business outcomes. Case studies and ROI data rather than feature lists.",
        "signal": "definitional_gap",
        "signal_label": "Definitional Gap",
        "cluster_theme": "Students understand diffusion theory but cannot explain crossing the chasm",
        "faculty_insight": "Students focus on marketing changes at the chasm but miss operational and product design shifts required — whole product concept, different support model.",
        "recommended_action": "Assign Geoffrey Moore's 'whole product' concept as supplementary reading to deepen understanding of chasm-crossing organizational requirements.",
        "confidence": "medium",
    },

    # ── user_led_adoption ─── 4 reflections
    {
        "topic_id": "user_led_adoption",
        "topic_label": "User-Led Adoption of Emerging Technologies",
        "q1": "Lead user theory says the most innovative users often develop solutions ahead of manufacturers. This is different from just using a product — these users actively create.",
        "followup_q": "How do companies decide whether to embrace lead user innovations or view them as threats to product control?",
        "q2": "It depends on the company's business model. Open platforms like GitHub embrace it because user contributions make the platform more valuable. Closed systems like Apple are more restrictive.",
        "q3": "I'd apply lead user theory to a medical device company — identify surgeons who are modifying existing devices and involve them in R&D early to co-develop next-generation products.",
        "signal": "surface_understanding",
        "signal_label": "Surface Understanding",
        "cluster_theme": "Students understand Agentic AI definition but struggle with business workflow application",
        "faculty_insight": "Students grasp lead user identification but overlook the governance and IP challenges companies face when integrating user-generated innovations.",
        "recommended_action": "Use the GoPro case study — how user-created content shaped product development — to explore the governance dimension of user-led innovation.",
        "confidence": "medium",
    },
    {
        "topic_id": "user_led_adoption",
        "topic_label": "User-Led Adoption of Emerging Technologies",
        "q1": "User-led adoption means users drive how a technology gets adopted. They sometimes use products in ways the manufacturer never intended, which can lead to new innovations.",
        "followup_q": "What conditions make it more likely that user adaptations will be adopted by the manufacturer rather than suppressed?",
        "q2": "I think when the user adaptation is clearly better or more popular than the original feature. Companies want to give users what they want so if something becomes popular they'll build it officially.",
        "q3": "Twitter is a good example — retweets were invented by users before Twitter made it an official feature. I'd look for similar emergent behaviors in any platform I was running.",
        "signal": "surface_understanding",
        "signal_label": "Surface Understanding",
        "cluster_theme": "Students understand Agentic AI definition but struggle with business workflow application",
        "faculty_insight": "Students identify user-driven feature emergence but conflate adoption (using a product) with innovation (modifying or creating new uses of it).",
        "recommended_action": "Use a definitional exercise: map 5 examples on a spectrum from pure adoption to pure user innovation to clarify the concept boundary.",
        "confidence": "medium",
    },
    {
        "topic_id": "user_led_adoption",
        "topic_label": "User-Led Adoption of Emerging Technologies",
        "q1": "I understand that users can drive technology adoption through community use and modification. Open source software is a major example where users contribute to the core product.",
        "followup_q": "Why do some open-source communities sustain long-term innovation while others lose momentum?",
        "q2": "Governance and clear contribution rules make communities last. Without structure it becomes chaotic. Also commercial backing helps — like how Red Hat supported Linux.",
        "q3": "I'd apply this to an enterprise software company considering open-sourcing a module. Community engagement could reduce R&D costs if the governance model is right.",
        "signal": "surface_understanding",
        "signal_label": "Surface Understanding",
        "cluster_theme": "Students understand Agentic AI definition but struggle with business workflow application",
        "faculty_insight": "Students use open source as the primary example of user innovation but miss the lead user theory's industrial and medical device origins.",
        "recommended_action": "Introduce Eric von Hippel's original lead user research in industrial contexts to broaden beyond software examples.",
        "confidence": "medium",
    },
    {
        "topic_id": "user_led_adoption",
        "topic_label": "User-Led Adoption of Emerging Technologies",
        "q1": "Lead users solve problems that mainstream users will face in the future. By studying lead users companies can get ahead of market needs.",
        "followup_q": "How would a company practically identify its lead users, and what makes this process difficult to operationalize?",
        "q2": "They could look at who is most engaged in forums, who files the most support requests with enhancement ideas, or who modifies the product. But it's hard because most users don't say they're lead users.",
        "q3": "For a B2B software company I'd set up a customer advisory board focused specifically on power users who stretch the product limits. Their workarounds often show where the product roadmap should go.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Application Barrier",
        "faculty_insight": "Student proposes a reasonable identification method but does not connect it to von Hippel's formal lead user methodology with pyramiding and screening.",
        "recommended_action": "Assign the lead user methodology process: pyramiding interviews, screening criteria, and workshop design as a structured identification protocol.",
        "confidence": "medium",
    },

    # ── classification_strategy ─── 3 reflections
    {
        "topic_id": "classification_strategy",
        "topic_label": "Emerging Technologies Classification and Adoption Strategy",
        "q1": "Technology classification helps you decide when to adopt. The pioneer strategy is early and risky, fast follower is safer. The 3-Horizon framework splits the portfolio into now, emerging, and future.",
        "followup_q": "How do you decide which horizon a technology belongs to for your specific organization, not just generically?",
        "q2": "It depends on how mature the technology is in your industry specifically, not just overall. A technology could be Horizon 1 for a tech company but Horizon 3 for a traditional bank.",
        "q3": "I'd use this for a manufacturing company evaluating AI quality control. For them it might be Horizon 2 because they're behind tech-native companies but it's no longer experimental.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Students confuse hype with real adoption readiness",
        "faculty_insight": "Students apply classification frameworks at a surface level but miss that organizational readiness must be assessed separately from technology maturity.",
        "recommended_action": "Introduce a two-axis readiness matrix: technology maturity (x) vs. organizational capability (y) to expose the gap students are missing.",
        "confidence": "high",
    },
    {
        "topic_id": "classification_strategy",
        "topic_label": "Emerging Technologies Classification and Adoption Strategy",
        "q1": "Classification frameworks let you sort technologies by maturity and impact. The key decision is whether to be an early adopter or wait for the technology to mature.",
        "followup_q": "What are the hidden costs of waiting for a technology to mature — what does the wait-and-see strategy actually risk?",
        "q2": "You risk letting competitors get ahead. But also the switching costs might be higher if you wait because the market has standardized around a competitor's platform.",
        "q3": "In retail I'd classify RFID as a mature technology now, so I'd adopt immediately. Computer vision checkout is still emerging so I'd monitor but not invest yet.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Students confuse hype with real adoption readiness",
        "faculty_insight": "Students identify competitive risk in waiting but miss regulatory, talent, and organizational change management risks of premature adoption.",
        "recommended_action": "Use a risk ledger exercise: for a given technology, list the costs of adopting too early vs. adopting too late and have students weigh them.",
        "confidence": "medium",
    },
    {
        "topic_id": "classification_strategy",
        "topic_label": "Emerging Technologies Classification and Adoption Strategy",
        "q1": "I found the idea of technology portfolio management interesting. You can't just evaluate one technology in isolation — you have to think about how your whole tech portfolio fits together.",
        "followup_q": "How does portfolio thinking change your evaluation of a single technology you're considering adopting?",
        "q2": "If you already have complementary technology in your portfolio, a new technology might be easier to integrate and deliver more value. If it's completely standalone it's harder to justify.",
        "q3": "For a hospital system, I'd evaluate AI diagnostics alongside existing imaging infrastructure. If the AI integrates with current systems the ROI picture changes significantly.",
        "signal": "applied_transfer_difficulty",
        "signal_label": "Applied-Transfer Difficulty",
        "cluster_theme": "Students confuse hype with real adoption readiness",
        "faculty_insight": "Students correctly identify portfolio interdependency but miss the standardization and technical debt dimensions of portfolio-level technology decisions.",
        "recommended_action": "Use a portfolio mapping exercise: draw the current technology stack, then overlay a new technology and identify integration points, dependencies, and gaps.",
        "confidence": "medium",
    },

    # ── implement_pov ─── 3 reflections
    {
        "topic_id": "implement_pov",
        "topic_label": "Implementing Emerging Technologies — Proof of Value (POV)",
        "q1": "POV is about proving that a technology delivers business value at scale. It's different from POC because POC just proves it works technically.",
        "followup_q": "If POC proves technical feasibility and POV proves business value, what specifically needs to be true for a POV to justify full deployment?",
        "q2": "The ROI needs to be clear and the organizational change management needs to be in place. You need stakeholder buy-in before you scale.",
        "q3": "For an insurer running an AI fraud detection POV, I'd define success as: 20% reduction in fraudulent claims with less than 5% false positive rate. If those metrics are hit, you have a case for deployment.",
        "signal": "definitional_gap",
        "signal_label": "Definitional Gap",
        "cluster_theme": "Students confuse POV with full deployment rather than a bounded test",
        "faculty_insight": "Students understand the POV goal but treat it as a smaller version of deployment rather than a controlled experiment with defined boundaries and kill criteria.",
        "recommended_action": "Introduce the concept of kill criteria and scope boundaries — a POV must be designed to fail fast as much as to succeed.",
        "confidence": "high",
    },
    {
        "topic_id": "implement_pov",
        "topic_label": "Implementing Emerging Technologies — Proof of Value (POV)",
        "q1": "I understand that POV comes after POC. The POV shows that the technology can deliver value in a real business setting, not just a lab environment.",
        "followup_q": "What makes organizational resistance a distinct failure mode for POV — separate from technical or financial failure?",
        "q2": "People might not use the technology even if it works. Change management is hard — employees resist new workflows especially if they feel threatened by automation.",
        "q3": "A logistics company testing route optimization AI: even if the algorithm works, drivers might not follow its recommendations if they distrust it. User adoption is a POV risk.",
        "signal": "definitional_gap",
        "signal_label": "Definitional Gap",
        "cluster_theme": "Students confuse POV with full deployment rather than a bounded test",
        "faculty_insight": "Students identify resistance as a risk but do not connect it to POV design — a well-designed POV includes change management as a measurable success criterion.",
        "recommended_action": "Add change management readiness as an explicit success criterion in POV design templates. Show examples where technology worked but POV failed due to adoption.",
        "confidence": "high",
    },
    {
        "topic_id": "implement_pov",
        "topic_label": "Implementing Emerging Technologies — Proof of Value (POV)",
        "q1": "Proof of Value quantifies whether a technology is worth scaling. You have to measure business impact in a controlled environment before committing to full deployment.",
        "followup_q": "How do you ensure the POV environment is representative enough that its results are reliable predictors of full deployment success?",
        "q2": "You have to pick the right scope — not so small it's not representative but not so large it becomes a full deployment. A single department or geography is usually a good middle ground.",
        "q3": "For a bank testing AI trade finance with two counterparties: the scope is small enough to control but the business process is real. If the results generalize you can expand.",
        "signal": "definitional_gap",
        "signal_label": "Definitional Gap",
        "cluster_theme": "Students confuse POV with full deployment rather than a bounded test",
        "faculty_insight": "Students identify scope selection as key but do not address representativeness testing — how to validate that POV conditions match production conditions.",
        "recommended_action": "Introduce POV scope validation: comparing POV environment characteristics to production environment on dimensions like volume, user type, integration complexity.",
        "confidence": "medium",
    },
]

DUMMY_COMPLETION_RECORDS = [
    {"student_name": "Aisha Okonkwo", "student_id": "N10234567", "topic_id": "intro_origins",
     "topic_label": "Introduction: Origins of Technology & Life Cycle Stages", "status": "submitted"},
    {"student_name": "Marcus Chen", "student_id": "N10345678", "topic_id": "intro_origins",
     "topic_label": "Introduction: Origins of Technology & Life Cycle Stages", "status": "submitted"},
    {"student_name": "Priya Nair", "student_id": "N10456789", "topic_id": "intro_origins",
     "topic_label": "Introduction: Origins of Technology & Life Cycle Stages", "status": "submitted"},
    {"student_name": "Jordan Williams", "student_id": "N10567890", "topic_id": "diffusion_innovation",
     "topic_label": "Diffusion of Innovation", "status": "submitted"},
    {"student_name": "Sofia Reyes", "student_id": "N10678901", "topic_id": "diffusion_innovation",
     "topic_label": "Diffusion of Innovation", "status": "submitted"},
    {"student_name": "Kwame Asante", "student_id": "N10789012", "topic_id": "diffusion_innovation",
     "topic_label": "Diffusion of Innovation", "status": "submitted"},
    {"student_name": "Emma Thornton", "student_id": "N10890123", "topic_id": "user_led_adoption",
     "topic_label": "User-Led Adoption of Emerging Technologies", "status": "submitted"},
    {"student_name": "Ravi Sharma", "student_id": "N10901234", "topic_id": "user_led_adoption",
     "topic_label": "User-Led Adoption of Emerging Technologies", "status": "submitted"},
    {"student_name": "Lena Fischer", "student_id": "N11012345", "topic_id": "classification_strategy",
     "topic_label": "Emerging Technologies Classification and Adoption Strategy", "status": "submitted"},
    {"student_name": "Olu Adeyemi", "student_id": "N11123456", "topic_id": "implement_pov",
     "topic_label": "Implementing Emerging Technologies — Proof of Value (POV)", "status": "submitted"},
]


# ─── Database ─────────────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _add_column_if_missing(conn, table, col, col_def):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
    except sqlite3.OperationalError:
        pass


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)

    # Table 1: completion_log — identifiable (name + student_id, NO reflection content)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS completion_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            student_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'submitted',
            submitted_at TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Table 2: anonymous_analysis — NO student identifiers ever
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anonymous_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anonymous_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            topic_label TEXT NOT NULL,
            q1 TEXT NOT NULL,
            followup_q TEXT NOT NULL,
            q2 TEXT NOT NULL,
            q3 TEXT NOT NULL,
            signal TEXT NOT NULL,
            signal_label TEXT NOT NULL,
            cluster_theme TEXT NOT NULL DEFAULT '',
            faculty_insight TEXT NOT NULL DEFAULT '',
            recommended_action TEXT NOT NULL DEFAULT '',
            confidence TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            is_demo INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.commit()

    # Migrations for existing DBs with older schemas
    for col, col_def in [
        ("anonymous_id", "TEXT NOT NULL DEFAULT ''"),
        ("cluster_theme", "TEXT NOT NULL DEFAULT ''"),
        ("faculty_insight", "TEXT NOT NULL DEFAULT ''"),
        ("recommended_action", "TEXT NOT NULL DEFAULT ''"),
        ("confidence", "TEXT NOT NULL DEFAULT ''"),
        ("is_demo", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        _add_column_if_missing(conn, "anonymous_analysis", col, col_def)

    _add_column_if_missing(conn, "completion_log", "is_demo", "INTEGER NOT NULL DEFAULT 0")

    conn.commit()
    conn.close()


def load_dummy_data():
    conn = sqlite3.connect(DB_PATH)
    base_ts = datetime.datetime(2026, 6, 1, 9, 0, 0)

    for i, r in enumerate(DUMMY_REFLECTIONS):
        ts = (base_ts + datetime.timedelta(hours=i * 2)).isoformat()
        anon_id = f"DEMO-{uuid.uuid4().hex[:8].upper()}"
        conn.execute(
            """INSERT INTO anonymous_analysis
               (anonymous_id, topic_id, topic_label, q1, followup_q, q2, q3,
                signal, signal_label, cluster_theme, faculty_insight,
                recommended_action, confidence, created_at, is_demo)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
            (
                anon_id, r["topic_id"], r["topic_label"],
                r["q1"], r["followup_q"], r["q2"], r["q3"],
                r["signal"], r["signal_label"],
                r["cluster_theme"], r["faculty_insight"],
                r["recommended_action"], r["confidence"],
                ts,
            ),
        )

    for i, rec in enumerate(DUMMY_COMPLETION_RECORDS):
        ts = (base_ts + datetime.timedelta(hours=i * 3)).isoformat()
        conn.execute(
            """INSERT INTO completion_log
               (student_name, student_id, topic_id, topic_label, status, submitted_at, is_demo)
               VALUES (?,?,?,?,?,?,1)""",
            (rec["student_name"], rec["student_id"],
             rec["topic_id"], rec["topic_label"], rec["status"], ts),
        )

    conn.commit()
    conn.close()


def clear_dummy_data():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM anonymous_analysis WHERE is_demo = 1")
    conn.execute("DELETE FROM completion_log WHERE is_demo = 1")
    conn.commit()
    conn.close()


# ─── AI helpers ───────────────────────────────────────────────────────────────
def generate_followup_question(topic_id: str, q1: str) -> str:
    topic = TOPIC_MAP.get(topic_id, {})
    topic_label = topic.get("label", topic_id)
    objectives = "\n".join(f"- {o}" for o in topic.get("objectives", []))
    confusions = "\n".join(f"- {c}" for c in topic.get("common_confusions", []))

    prompt = f"""You are a Socratic learning coach for an NYU graduate seminar on Emerging Technologies.
A student has just reflected on the topic "{topic_label}".

Learning objectives:
{objectives}

Common student confusions to probe:
{confusions}

Student's initial reflection (Q1):
"{q1}"

Generate exactly ONE thoughtful Socratic follow-up question that:
1. Probes deeper into their stated understanding without repeating their words
2. Connects their reflection to a real-world business or technology context
3. Is open-ended and non-judgmental
4. Is concise (one sentence, under 30 words)
5. Targets a common confusion or an unstated assumption in their answer

Return ONLY the question text, no preamble or quotes."""

    response = get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=80,
        temperature=0.7,
    )
    return response.choices[0].message.content.strip().strip('"')


def classify_reflection(topic_id: str, q1: str, q2: str, q3: str) -> str:
    topic = TOPIC_MAP.get(topic_id, {})
    topic_label = topic.get("label", topic_id)
    key_concepts = ", ".join(topic.get("key_concepts", []))

    prompt = f"""You are an educational analyst for an NYU Emerging Technologies graduate course.
Classify a student's anonymous reflection into exactly ONE learning signal.

Topic: {topic_label}
Key concepts: {key_concepts}

Student responses:
Q1 (What did you learn?): "{q1}"
Q2 (Socratic follow-up answer): "{q2}"
Q3 (Real-world application): "{q3}"

Learning signals:
- comprehension: Solid, nuanced understanding — student can explain clearly and apply accurately
- surface_understanding: Knows vocabulary and surface facts but lacks depth or mechanistic insight
- definitional_gap: Core concepts or terms appear unclear, confused, or conflated
- applied_transfer_difficulty: Understands in isolation but struggles to transfer to novel contexts
- pacing_concern: Tone or content suggests pacing issues (too fast, overwhelmed, or disengaged)
- support_need: Signals a need for additional resources, guidance, or instructor check-in

Return ONLY the signal key exactly as listed (e.g., "comprehension"). No explanation."""

    response = get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=20,
        temperature=0.2,
    )
    result = response.choices[0].message.content.strip().lower().strip('"').strip("'")
    return result if result in SIGNALS else "surface_understanding"


# ─── Routes — Student side ─────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", courses=COURSE_DATA["courses"])


@app.route("/student")
def student():
    return redirect(url_for("index"))


@app.route("/reflect")
def reflect():
    topic_id = request.args.get("topic", "")
    if not topic_id or topic_id not in TOPIC_MAP:
        return redirect(url_for("index"))
    topic = TOPIC_MAP[topic_id]
    return render_template("reflect.html", topic_id=topic_id, topic=topic)


@app.route("/reflect/followup", methods=["POST"])
def followup():
    data = request.get_json(silent=True) or {}
    topic_id = data.get("topic_id", "").strip()
    q1 = data.get("q1", "").strip()

    if not topic_id or topic_id not in TOPIC_MAP:
        return jsonify({"error": "Invalid topic."}), 400
    if len(q1) < 20:
        return jsonify({"error": "Response is too short."}), 400

    try:
        question = generate_followup_question(topic_id, q1)
        return jsonify({"question": question})
    except Exception as e:
        app.logger.error("OpenAI error in followup: %s", e)
        return jsonify({"error": "Could not generate a follow-up question. Please check your API key."}), 500


@app.route("/reflect/submit", methods=["POST"])
def submit():
    student_name = request.form.get("student_name", "").strip()
    student_id = request.form.get("student_id", "").strip()

    topic_id = request.form.get("topic_id", "").strip()
    q1 = request.form.get("q1", "").strip()
    followup_q = request.form.get("followup_q", "").strip()
    q2 = request.form.get("q2", "").strip()
    q3 = request.form.get("q3", "").strip()

    if not all([student_name, student_id, topic_id, q1, followup_q, q2, q3]):
        return redirect(url_for("reflect", topic=topic_id))
    if topic_id not in TOPIC_MAP:
        return redirect(url_for("index"))

    topic = TOPIC_MAP[topic_id]
    now = datetime.datetime.utcnow().isoformat()

    try:
        signal = classify_reflection(topic_id, q1, q2, q3)
    except Exception as e:
        app.logger.error("OpenAI error in classify: %s", e)
        signal = "surface_understanding"

    signal_label = SIGNAL_LABELS.get(signal, signal)
    meta = CLUSTER_META.get(signal, {})
    anon_id = f"ANON-{uuid.uuid4().hex[:8].upper()}"

    db = get_db()

    # Table 1: completion_log — identity ONLY, no reflection content
    db.execute(
        """INSERT INTO completion_log
           (student_name, student_id, topic_id, topic_label, status, submitted_at, is_demo)
           VALUES (?, ?, ?, ?, 'submitted', ?, 0)""",
        (student_name, student_id, topic_id, topic["label"], now),
    )

    # Table 2: anonymous_analysis — content ONLY, no identity
    db.execute(
        """INSERT INTO anonymous_analysis
           (anonymous_id, topic_id, topic_label, q1, followup_q, q2, q3,
            signal, signal_label, cluster_theme, faculty_insight,
            recommended_action, confidence, created_at, is_demo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, 0)""",
        (
            anon_id, topic_id, topic["label"], q1, followup_q, q2, q3,
            signal, signal_label,
            meta.get("cluster_theme", ""),
            meta.get("faculty_insight", ""),
            meta.get("recommended_action", ""),
            now,
        ),
    )

    db.commit()
    return render_template("thank_you.html")


# ─── Routes — Faculty side ─────────────────────────────────────────────────────
@app.route("/faculty")
def faculty():
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    db = get_db()
    selected_topic = request.args.get("topic", "")

    where_clauses = []
    params = []
    if selected_topic:
        where_clauses.append("topic_id = ?")
        params.append(selected_topic)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total = db.execute(
        f"SELECT COUNT(*) FROM anonymous_analysis {where_sql}", params
    ).fetchone()[0]

    has_demo = db.execute(
        "SELECT COUNT(*) FROM anonymous_analysis WHERE is_demo = 1"
    ).fetchone()[0] > 0

    signal_rows = db.execute(
        f"SELECT signal, COUNT(*) as cnt FROM anonymous_analysis {where_sql} "
        "GROUP BY signal ORDER BY cnt DESC",
        params,
    ).fetchall()
    signal_counts = {r["signal"]: r["cnt"] for r in signal_rows}

    signal_dist = []
    for sig in SIGNALS:
        cnt = signal_counts.get(sig, 0)
        suppressed = 0 < cnt < AGGREGATION_THRESHOLD
        signal_dist.append({
            "signal": sig,
            "label": SIGNAL_LABELS[sig],
            "css": SIGNAL_CSS[sig],
            "count": cnt if not suppressed else 0,
            "pct": round(cnt / total * 100) if (total > 0 and not suppressed) else 0,
            "suppressed": suppressed,
            "desc": SIGNAL_DESCRIPTIONS[sig],
        })

    clusters = []
    suppressed_count = 0
    for sig in SIGNALS:
        cnt = signal_counts.get(sig, 0)
        if cnt == 0:
            continue
        if cnt < AGGREGATION_THRESHOLD:
            suppressed_count += 1
            continue
        meta = CLUSTER_META.get(sig, {})
        clusters.append({
            "signal": sig,
            "signal_type": SIGNAL_LABELS[sig],
            "css": SIGNAL_CSS[sig],
            "cluster_theme": meta.get("cluster_theme", ""),
            "count": cnt,
            "faculty_insight": meta.get("faculty_insight", ""),
            "recommended_action": meta.get("recommended_action", ""),
        })
    clusters.sort(key=lambda x: x["count"], reverse=True)

    topic_rows = db.execute(
        f"""SELECT topic_id, topic_label,
               COUNT(*) as cnt,
               GROUP_CONCAT(signal) as signals
            FROM anonymous_analysis {where_sql}
            GROUP BY topic_id, topic_label
            ORDER BY cnt DESC LIMIT 11""",
        params,
    ).fetchall()

    topic_patterns = []
    for r in topic_rows:
        sigs_raw = r["signals"].split(",") if r["signals"] else []
        topic_sig_counts: dict = {}
        for s in sigs_raw:
            topic_sig_counts[s] = topic_sig_counts.get(s, 0) + 1
        visible_sigs = []
        has_suppressed = False
        for s, c in sorted(topic_sig_counts.items(), key=lambda x: -x[1]):
            if c < AGGREGATION_THRESHOLD:
                has_suppressed = True
            else:
                visible_sigs.append(s)
        topic_info = TOPIC_MAP.get(r["topic_id"], {})
        topic_patterns.append({
            "topic_id": r["topic_id"],
            "topic_label": r["topic_label"],
            "week": topic_info.get("week", ""),
            "count": r["cnt"],
            "top_signals": [
                {"signal": s, "label": SIGNAL_LABELS.get(s, s), "css": SIGNAL_CSS.get(s, "")}
                for s in visible_sigs[:3]
            ],
            "suppressed": has_suppressed,
        })

    action_signals = []
    gap_count = signal_counts.get("definitional_gap", 0)
    apply_count = signal_counts.get("applied_transfer_difficulty", 0)
    pace_count = signal_counts.get("pacing_concern", 0)
    support_count = signal_counts.get("support_need", 0)
    surface_count = signal_counts.get("surface_understanding", 0)

    if total > 0:
        if gap_count >= AGGREGATION_THRESHOLD and gap_count / total >= 0.25:
            action_signals.append({
                "level": "urgent",
                "title": "Terminology gaps detected",
                "desc": (
                    f"{gap_count} of {total} reflections ({round(gap_count/total*100)}%) show definitional gaps. "
                    "Consider a vocabulary review activity. Faculty review required before action."
                ),
            })
        if apply_count >= AGGREGATION_THRESHOLD and apply_count / total >= 0.3:
            action_signals.append({
                "level": "warn",
                "title": "Application transfer difficulty",
                "desc": (
                    f"{apply_count} reflections signal difficulty applying concepts to real scenarios. "
                    "Scaffolded case exercises may help. Faculty review required before action."
                ),
            })
        if pace_count >= AGGREGATION_THRESHOLD and pace_count / total >= 0.2:
            action_signals.append({
                "level": "warn",
                "title": "Pacing concerns emerging",
                "desc": (
                    f"{pace_count} reflections suggest pacing issues. "
                    "A quick pulse check is recommended. Faculty review required before action."
                ),
            })
        if support_count >= AGGREGATION_THRESHOLD:
            action_signals.append({
                "level": "urgent",
                "title": "Support requests flagged",
                "desc": (
                    f"{support_count} students may need additional support. "
                    "Consider office hours or supplementary materials. Faculty review required before action."
                ),
            })
        if surface_count >= AGGREGATION_THRESHOLD and surface_count / total >= 0.4 and not action_signals:
            action_signals.append({
                "level": "info",
                "title": "Surface-level understanding dominant",
                "desc": (
                    f"{surface_count} reflections show surface understanding. "
                    "Deeper Socratic discussion may help consolidate learning. Faculty review required."
                ),
            })

    if not action_signals and total > 0:
        action_signals.append({
            "level": "info",
            "title": "No critical patterns detected",
            "desc": "Current reflections show a healthy distribution. Continue monitoring as more data is collected.",
        })

    unique_topics = db.execute(
        f"SELECT COUNT(DISTINCT topic_id) FROM anonymous_analysis {where_sql}", params
    ).fetchone()[0]
    comprehension_count = signal_counts.get("comprehension", 0)
    comprehension_rate = round(comprehension_count / total * 100) if total > 0 else 0

    topics_for_filter = db.execute(
        "SELECT DISTINCT topic_id, topic_label FROM anonymous_analysis ORDER BY topic_label"
    ).fetchall()

    return render_template(
        "dashboard.html",
        total=total,
        unique_topics=unique_topics,
        comprehension_rate=comprehension_rate,
        signal_dist=signal_dist,
        clusters=clusters,
        suppressed_count=suppressed_count,
        topic_patterns=topic_patterns,
        action_signals=action_signals,
        topics_for_filter=topics_for_filter,
        selected_topic=selected_topic,
        has_demo=has_demo,
    )


@app.route("/dashboard/load-demo", methods=["POST"])
def load_demo():
    load_dummy_data()
    return redirect(url_for("dashboard"))


@app.route("/dashboard/clear-demo", methods=["POST"])
def clear_demo():
    clear_dummy_data()
    return redirect(url_for("dashboard"))


@app.route("/completion")
def completion():
    db = get_db()
    selected_topic = request.args.get("topic", "")

    where_clauses = []
    params = []
    if selected_topic:
        where_clauses.append("topic_id = ?")
        params.append(selected_topic)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    total_submissions = db.execute(
        f"SELECT COUNT(*) FROM completion_log {where_sql}", params
    ).fetchone()[0]

    unique_students = db.execute(
        f"SELECT COUNT(DISTINCT student_id) FROM completion_log {where_sql}", params
    ).fetchone()[0]

    topics_with_submissions = db.execute(
        f"SELECT COUNT(DISTINCT topic_id) FROM completion_log {where_sql}", params
    ).fetchone()[0]

    # Shows only who submitted — NO reflection content, NO signal, NO AI classification
    rows = db.execute(
        f"""SELECT student_name, student_id, topic_id, topic_label, submitted_at, is_demo
            FROM completion_log {where_sql}
            ORDER BY topic_id, submitted_at""",
        params,
    ).fetchall()

    groups: dict = {}
    for row in rows:
        tid = row["topic_id"]
        if tid not in groups:
            topic_info = TOPIC_MAP.get(tid, {})
            groups[tid] = {
                "topic_id": tid,
                "topic_label": row["topic_label"],
                "week": topic_info.get("week", ""),
                "submissions": [],
            }
        groups[tid]["submissions"].append({
            "student_name": row["student_name"],
            "student_id": row["student_id"],
            "submitted_at": row["submitted_at"],
            "is_demo": row["is_demo"],
        })

    by_topic = sorted(groups.values(), key=lambda x: x.get("week") or 0)

    all_topics = [
        {"id": t["id"], "label": t["label"], "week": t.get("week", "")}
        for course in COURSE_DATA["courses"]
        for t in course["topics"]
    ]

    has_demo = db.execute(
        "SELECT COUNT(*) FROM completion_log WHERE is_demo = 1"
    ).fetchone()[0] > 0

    return render_template(
        "completion.html",
        total_submissions=total_submissions,
        unique_students=unique_students,
        topics_with_submissions=topics_with_submissions,
        by_topic=by_topic,
        all_topics=all_topics,
        selected_topic=selected_topic,
        has_demo=has_demo,
    )


@app.route("/governance")
def governance():
    return render_template("governance.html")


# ─── API: OpenAI key test (server-side only — key never exposed to browser) ───
def _test_key_safe(api_key: str) -> tuple[bool, str]:
    """Test an API key. Returns (ok, message). Never includes the key in the message."""
    if not api_key or api_key == "unset":
        return False, "No API key is set. Use the API Setup page or add OPENAI_API_KEY to Replit Secrets."
    try:
        test_client = OpenAI(api_key=api_key)
        test_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
            max_tokens=5,
        )
        app.logger.info("OpenAI key test: SUCCESS")
        return True, "OpenAI API key is valid and responding."
    except Exception as e:
        error_str = str(e)
        app.logger.error("OpenAI key test FAILED: %s", error_str)
        if "insufficient_quota" in error_str:
            msg = "insufficient_quota — API key is valid but billing quota is exhausted. Add credits at platform.openai.com/account/billing."
        elif "invalid_api_key" in error_str or "Incorrect API key" in error_str:
            msg = "invalid_api_key — The key provided is not recognised by OpenAI. Double-check the value."
        elif "model_not_found" in error_str:
            msg = "model_not_found — gpt-4o-mini is not available on this account."
        elif "permission" in error_str.lower():
            msg = "permission_error — Your API key does not have access to this model or endpoint."
        else:
            msg = f"OpenAI error: {error_str[:300]}"
        return False, msg


@app.route("/api/test-openai")
def test_openai():
    key = _runtime_api_key or os.environ.get("OPENAI_API_KEY", "")
    ok, msg = _test_key_safe(key)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 500)


# ─── Routes — API setup (demo-only key management) ───────────────────────────
@app.route("/setup-api-key")
def setup_api_key():
    has_runtime = bool(_runtime_api_key)
    has_env = bool(os.environ.get("OPENAI_API_KEY", ""))
    active_source = "runtime" if has_runtime else ("env" if has_env else "none")

    prefix = ""
    length = 0
    if has_runtime and _runtime_api_key:
        prefix = _runtime_api_key[:7]
        length = len(_runtime_api_key)
    elif has_env:
        env_key = os.environ.get("OPENAI_API_KEY", "")
        prefix = env_key[:7]
        length = len(env_key)

    return render_template(
        "setup_api_key.html",
        has_runtime=has_runtime,
        has_env=has_env,
        active_source=active_source,
        prefix=prefix,
        length=length,
    )


@app.route("/setup-api-key/save", methods=["POST"])
def save_api_key():
    global _runtime_api_key
    data = request.get_json(silent=True) or {}
    key = data.get("api_key", "").strip()

    if not key:
        return jsonify({"ok": False, "message": "No key provided."}), 400
    if not key.startswith("sk-"):
        return jsonify({"ok": False, "message": "Key does not look like a valid OpenAI key (should start with sk-)."}), 400

    _runtime_api_key = key
    app.logger.info("Runtime API key updated (length=%d, prefix=%s)", len(key), key[:7])

    return jsonify({
        "ok": True,
        "loaded": True,
        "prefix": key[:7],
        "length": len(key),
        "message": "Key saved to server memory for this session.",
    })


@app.route("/setup-api-key/test", methods=["POST"])
def test_api_key_setup():
    key = _runtime_api_key or os.environ.get("OPENAI_API_KEY", "")
    ok, msg = _test_key_safe(key)
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 500)


# ─── Init & run ───────────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
