import React, { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useUser } from "@clerk/clerk-react";

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

function Analysis() {
  const { user } = useUser();
  const location = useLocation();

  const [analysisData, setAnalysisData] = useState(null);
  const [emotionChartData, setEmotionChartData] = useState(null);

  /* ────────── fetch analysis ────────── */
  useEffect(() => {
    const fetchAnalysis = async () => {
      if (!user?.primaryEmailAddress) return;
      const interviewId = location.state?.interviewId;
      if (!interviewId) return;
      try {
        const res = await fetch("http://localhost:5000/api/getAnalysis", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Clerk-User-Email": user.primaryEmailAddress.emailAddress
          },
          body: JSON.stringify({ interviewId })
        });
        const data = await res.json();
        if (!data.error) setAnalysisData(data);
      } catch (err) {
        console.error("Analysis fetch error:", err);
      }
    };
    fetchAnalysis();
  }, [user, location.state]);

  /* ────────── build emotion chart ────────── */
  useEffect(() => {
    if (!analysisData?.emotionTimeline) return;
    const timeline = analysisData.emotionTimeline;
    const EMOTIONS = [
      "angry",
      "disgust",
      "fear",
      "happy",
      "neutral",
      "sad",
      "surprise"
    ];
    const COLORS = [
      "#e6194B",
      "#3cb44b",
      "#911eb4",
      "#ffe119",
      "#4363d8",
      "#f58231",
      "#42d4f4"
    ];
    const labels = timeline.map((e) => new Date(e.timestamp).toLocaleTimeString());

    const datasets = EMOTIONS.map((emo, i) => ({
      label: emo,
      data: timeline.map((t) => (t.distribution || {})[emo] || 0),
      borderWidth: 2,
      borderColor: COLORS[i],
      backgroundColor: COLORS[i],
      tension: 0.2
    }));
    setEmotionChartData({ labels, datasets });
  }, [analysisData]);

  /* ────────── loading state ────────── */
  if (!analysisData)
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h1 style={styles.headerTitle}>Loading Final Summary...</h1>
        </div>
        <div style={{ textAlign: "center", marginTop: 50 }}>
          <h3>Please wait while we gather your results.</h3>
        </div>
      </div>
    );

  /* ────────── destructure data ────────── */
  const {
    status,
    completed_at,
    final_summary,
    avgRating,
    fillerRate,
    totalWordsSpoken,
    skillAnalysis
  } = analysisData;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>Interview Analysis</h1>
        <p style={styles.headerSubtitle}>
          Detailed Soft-Skill &amp; Performance Insights
        </p>
      </div>

      <div style={styles.mainContent}>
        {/* stats */}
        <div style={styles.statsRow}>
          <StatCard title="Average Rating" value={`${avgRating?.toFixed(2) || "N/A"} / 5`} />
          <StatCard title="Filler Rate" value={`${(fillerRate * 100).toFixed(2)}%`} />
          <StatCard title="Words Spoken" value={totalWordsSpoken || 0} />
        </div>

        {/* overall summary */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>Overall Summary</h2>
          <p style={styles.summaryText}>
            <strong>Status:</strong> {status}
            {completed_at && ` (Completed at ${completed_at})`}
          </p>
          <p style={styles.summaryText}>{final_summary || "No final summary."}</p>
        </div>

        {/* soft-skill analysis */}
        {skillAnalysis && (
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Soft-Skill Breakdown</h2>
            {Object.entries(skillAnalysis).map(([skill, txt]) => (
              <div key={skill} style={styles.skillSection}>
                <h3 style={styles.skillTitle}>{capitalize(skill)} Skills</h3>
                {renderBulletPoints(txt)}
              </div>
            ))}
          </div>
        )}

        {/* emotion chart */}
        <div style={styles.chartContainer}>
          <h2 style={styles.cardTitle}>Emotion Timeline</h2>
          {emotionChartData ? (
            <div style={{ maxWidth: 800, margin: "0 auto" }}>
              <Line
                data={emotionChartData}
                options={{
                  responsive: true,
                  plugins: {
                    legend: { position: "top" },
                    title: { display: true, text: "Emotions Over Time" }
                  },
                  scales: {
                    y: {
                      beginAtZero: true,
                      title: { display: true, text: "Probability (%)" }
                    }
                  }
                }}
              />
            </div>
          ) : (
            <p>No emotion data available.</p>
          )}
        </div>
      </div>
    </div>
  );
}

/* ────────── helper components ────────── */
const StatCard = ({ title, value }) => (
  <div style={styles.statCard}>
    <h3 style={styles.statTitle}>{title}</h3>
    <p style={styles.statValue}>{value}</p>
  </div>
);

/* ────────── bullet-point renderer ────────── */
function renderBulletPoints(text) {
  if (!text?.trim()) return <p style={{ color: "#999" }}>No analysis provided.</p>;

  /** 1. normalise line breaks */
  const prep = text
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n")
    // ensure every bullet marker starts on its own line
    .replace(/([*•\-])\s+/g, "\n$1 ");

  /** 2. capture bullets of form *, -, • */
  const bulletRegex = /^[\s*•\-]+\s?(.*)$/gm;
  const bullets = [];
  let match;
  while ((match = bulletRegex.exec(prep))) {
    const line = match[1].trim();
    if (line) bullets.push(line);
  }

  return bullets.length ? (
    <ul style={{ marginLeft: "1.5rem", lineHeight: 1.6 }}>
      {bullets.map((b, i) => (
        <li key={i} dangerouslySetInnerHTML={{ __html: b }} />
      ))}
    </ul>
  ) : (
    <p style={{ marginLeft: "1rem" }}>{text}</p>
  );
}

const capitalize = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : "");

/* ────────── styles (unchanged aside from minor tweaks) ────────── */
const styles = {
  container: {
    display: "flex",
    flexDirection: "column",
    fontFamily: "Poppins, sans-serif",
    minHeight: "100vh"
  },
  header: {
    padding: "2rem 1rem",
    background: "linear-gradient(135deg,#6EE2F5 0%,#6454F0 100%)",
    textAlign: "center",
    color: "#fff",
    marginBottom: "2rem"
  },
  headerTitle: { margin: 0, fontWeight: 600 },
  headerSubtitle: { marginTop: 8, opacity: 0.9 },
  mainContent: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    padding: "0 1rem 2rem",
    flex: 1
  },
  statsRow: {
    display: "flex",
    gap: "1rem",
    flexWrap: "wrap",
    justifyContent: "center",
    marginBottom: "2rem"
  },
  statCard: {
    backgroundColor: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
    padding: "1rem 1.5rem",
    minWidth: 160,
    textAlign: "center"
  },
  statTitle: { margin: 0, fontWeight: 600, marginBottom: 4 },
  statValue: { margin: 0, fontSize: "1.3rem", color: "#6454F0", fontWeight: 500 },
  card: {
    backgroundColor: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
    padding: "1.5rem",
    maxWidth: 800,
    width: "100%",
    marginBottom: "2rem"
  },
  cardTitle: { marginTop: 0, marginBottom: "1rem", fontWeight: 600 },
  summaryText: { marginBottom: "1rem", color: "#444", lineHeight: 1.5 },
  skillSection: { marginBottom: "1.5rem" },
  skillTitle: {
    margin: 0,
    marginBottom: 8,
    fontWeight: 600,
    fontSize: "1.05rem",
    color: "#333"
  },
  chartContainer: { maxWidth: 900, width: "100%", textAlign: "center" }
};

export default Analysis;
