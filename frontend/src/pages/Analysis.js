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
        // This route returns final_summary + emotionTimeline
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

  // build chart data
  useEffect(() => {
    if (analysisData && analysisData.emotionTimeline) {
      const timeline = analysisData.emotionTimeline;
      const EMOTIONS_TO_PLOT = ["happy", "neutral", "angry", "surprise"];

      // define colors
      const COLORS = ["#ff0000", "#00c853", "#2979ff", "#ff6f00"];
      // red, green, blue, orange

      const labels = timeline.map(entry => {
        const t = new Date(entry.timestamp);
        return t.toLocaleTimeString();
      });

      const datasets = EMOTIONS_TO_PLOT.map((emotionKey, i) => {
        const dataPoints = timeline.map(entry => {
          const dist = entry.distribution || {};
          return dist[emotionKey] || 0;
        });
        return {
          label: emotionKey,
          data: dataPoints,
          borderWidth: 2,
          borderColor: COLORS[i % COLORS.length],
          backgroundColor: COLORS[i % COLORS.length]
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
      <div style={{ textAlign:'center', marginTop:'50px'}}>
        <h2>Loading Final Summary...</h2>
      </div>
    );
  }

  // we only have final_summary + timeline
  const { status, completed_at, final_summary } = analysisData;

  return (
    <div style={{ textAlign:'center', marginTop:'30px' }}>
      <h2>Final Interview Summary</h2>
      <p>Status: {status} {completed_at && `(Completed at ${completed_at})`}</p>

      {/* Soft skill summary from LLM */}
      <div style={{ margin:'20px auto', maxWidth:'700px', textAlign:'left'}}>
        <h3>LLM Soft Skill Evaluation</h3>
        <p>{final_summary}</p>
      </div>

      {/* Emotion Chart */}
      <div style={{ marginTop:'40px', maxWidth:'800px', margin:'0 auto'}}>
        <h3>Emotion Timeline</h3>
        {emotionChartData ? (
          <Line data={emotionChartData} />
        ) : (
          <p>No emotion data available.</p>
        )}
      </div>
    </div>
  );
}

export default Analysis;
