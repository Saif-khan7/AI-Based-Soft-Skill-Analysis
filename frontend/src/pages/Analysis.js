// src/pages/Analysis.js

import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';

import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Line } from 'react-chartjs-2';

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

  useEffect(() => {
    const fetchAnalysis = async() => {
      if (!user?.primaryEmailAddress) {
        console.warn("No user email - not fetching analysis");
        return;
      }
      const interviewId = location.state?.interviewId;
      if(!interviewId) {
        console.warn("No interviewId in route state - can't fetch analysis");
        return;
      }
      try {
        // This route returns final_summary, skillAnalysis, overall stats, emotionTimeline, etc.
        const res = await fetch("http://localhost:5000/api/getAnalysis", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Clerk-User-Email": user.primaryEmailAddress.emailAddress
          },
          body: JSON.stringify({ interviewId })
        });
        const data = await res.json();
        if (data.error) {
          console.error("Analysis error:", data.error);
        } else {
          setAnalysisData(data);
        }
      } catch(err) {
        console.error("Analysis fetch error:", err);
      }
    };
    fetchAnalysis();
  }, [user, location.state]);

  // Build chart data for 7 emotions
  useEffect(() => {
    if (analysisData && analysisData.emotionTimeline) {
      const timeline = analysisData.emotionTimeline;
      
      // We'll now plot all seven emotions:
      const EMOTIONS_TO_PLOT = [
        "angry",
        "disgust",
        "fear",
        "happy",
        "neutral",
        "sad",
        "surprise"
      ];

      // define a distinct color array for each emotion
      // (7 bright colors)
      const COLORS = [
        "#e6194B", // bright red
        "#3cb44b", // green
        "#911eb4", // purple
        "#ffe119", // yellow
        "#4363d8", // blue
        "#f58231", // orange
        "#42d4f4"  // aqua/cyan
      ];

      const labels = timeline.map(entry => {
        const t = new Date(entry.timestamp);
        return t.toLocaleTimeString();
      });

      const datasets = EMOTIONS_TO_PLOT.map((emotionKey, i) => {
        const dataPoints = timeline.map(entry => {
          const dist = entry.distribution || {};
          // each distribution is e.g. {angry: 2.70, disgust: 0.001, ...}
          return dist[emotionKey] || 0;
        });
        return {
          label: emotionKey,
          data: dataPoints,
          borderWidth: 2,
          borderColor: COLORS[i % COLORS.length],
          backgroundColor: COLORS[i % COLORS.length],
          tension: 0.2  // slight curve to the line
        };
      });

      const chartData = {
        labels,
        datasets
      };
      setEmotionChartData(chartData);
    }
  }, [analysisData]);

  if (!analysisData) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h1 style={styles.headerTitle}>Loading Final Summary...</h1>
        </div>
        <div style={{ textAlign:'center', marginTop:'50px'}}>
          <h3>Please wait while we gather your results.</h3>
        </div>
      </div>
    );
  }

  const {
    status,
    completed_at,
    final_summary,
    avgRating,
    fillerRate,
    totalWordsSpoken,
    skillAnalysis,
    emotionTimeline
  } = analysisData;

  return (
    <div style={styles.container}>
      {/* Hero Header */}
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>Interview Analysis</h1>
        <p style={styles.headerSubtitle}>
          Detailed Soft Skill & Overall Performance Insights
        </p>
      </div>

      {/* Main Content */}
      <div style={styles.mainContent}>

        {/* Overall Stats Row */}
        <div style={styles.statsRow}>
          <div style={styles.statCard}>
            <h3 style={styles.statTitle}>Average Rating</h3>
            <p style={styles.statValue}>
              {avgRating ? avgRating.toFixed(2) : "N/A"} / 5
            </p>
          </div>
          <div style={styles.statCard}>
            <h3 style={styles.statTitle}>Filler Rate</h3>
            <p style={styles.statValue}>
              {(fillerRate * 100).toFixed(2)}%
            </p>
          </div>
          <div style={styles.statCard}>
            <h3 style={styles.statTitle}>Words Spoken</h3>
            <p style={styles.statValue}>
              {totalWordsSpoken || 0}
            </p>
          </div>
        </div>

        {/* Final Summary Card */}
        <div style={styles.card}>
          <h2 style={styles.cardTitle}>Overall Summary</h2>
          <p style={styles.summaryText}>
            <strong>Status:</strong> {status} {completed_at && `(Completed at ${completed_at})`}
          </p>
          <p style={styles.summaryText}>{final_summary || "No final summary."}</p>
        </div>

        {/* Soft Skill Analysis */}
        {skillAnalysis && (
          <div style={styles.card}>
            <h2 style={styles.cardTitle}>Soft Skill Breakdown</h2>
            {Object.keys(skillAnalysis).map((skillKey, idx) => {
              const analysisText = skillAnalysis[skillKey];
              return (
                <div key={idx} style={styles.skillSection}>
                  <h3 style={styles.skillTitle}>{capitalize(skillKey)} Skills</h3>
                  {renderBulletPoints(analysisText)}
                </div>
              );
            })}
          </div>
        )}

        {/* Emotion Timeline Chart */}
        <div style={styles.chartContainer}>
          <h2 style={styles.cardTitle}>Emotion Timeline</h2>
          {emotionChartData ? (
            <div style={{ maxWidth: '800px', margin: '0 auto' }}>
              <Line data={emotionChartData} options={{
                responsive: true,
                plugins: {
                  legend: {
                    position: 'top'
                  },
                  title: {
                    display: true,
                    text: 'Emotions Over Time'
                  }
                },
                scales: {
                  y: {
                    beginAtZero: true,
                    title: {
                      display: true,
                      text: 'Probability (%)'
                    }
                  }
                }
              }} />
            </div>
          ) : (
            <p>No emotion data available.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// Helper to display bullet points
function renderBulletPoints(text) {
  if (!text || text.trim().length === 0) {
    return <p style={{ color: '#999' }}>No analysis provided.</p>;
  }

  const lines = text.split('\n').map(l => l.trim()).filter(l => l);
  
  const bullets = [];
  for (let l of lines) {
    if (l.startsWith("-")) {
      bullets.push(l.substring(1).trim());
    }
  }

  if (bullets.length > 0) {
    return (
      <ul style={{ marginLeft: '1.5rem', lineHeight: 1.6 }}>
        {bullets.map((b, i) => <li key={i}>{b}</li>)}
      </ul>
    );
  } else {
    // If no lines start with "-", just show raw
    return <p style={{ marginLeft:'1rem' }}>{text}</p>;
  }
}

function capitalize(str) {
  if (!str) return "";
  return str.charAt(0).toUpperCase() + str.slice(1);
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    fontFamily: 'Poppins, sans-serif',
    minHeight: '100vh'
  },
  header: {
    padding: '2rem 1rem',
    background: 'linear-gradient(135deg, #6EE2F5 0%, #6454F0 100%)',
    textAlign: 'center',
    color: '#fff',
    marginBottom: '2rem'
  },
  headerTitle: {
    margin: 0,
    fontWeight: 600
  },
  headerSubtitle: {
    marginTop: '0.5rem',
    fontSize: '1rem',
    opacity: 0.9
  },
  mainContent: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '0 1rem 2rem',
    flex: 1
  },
  statsRow: {
    display: 'flex',
    gap: '1rem',
    flexWrap: 'wrap',
    justifyContent: 'center',
    marginBottom: '2rem'
  },
  statCard: {
    backgroundColor: '#fff',
    borderRadius: '8px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
    padding: '1rem 1.5rem',
    minWidth: '160px',
    textAlign: 'center'
  },
  statTitle: {
    margin: 0,
    fontWeight: 600,
    color: '#333',
    marginBottom: '0.3rem'
  },
  statValue: {
    margin: 0,
    fontSize: '1.3rem',
    color: '#6454F0',
    fontWeight: 500
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: '8px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
    padding: '1.5rem',
    maxWidth: '800px',
    width: '100%',
    marginBottom: '2rem'
  },
  cardTitle: {
    marginTop: 0,
    marginBottom: '1rem',
    fontWeight: 600,
    fontSize: '1.2rem'
  },
  summaryText: {
    marginBottom: '1rem',
    color: '#444',
    lineHeight: 1.5
  },
  skillSection: {
    marginBottom: '1.5rem'
  },
  skillTitle: {
    margin: 0,
    marginBottom: '0.5rem',
    fontWeight: 600,
    fontSize: '1.05rem',
    color: '#333'
  },
  chartContainer: {
    maxWidth: '900px',
    width: '100%',
    textAlign: 'center'
  }
};

export default Analysis;
