// src/pages/Analysis.js

import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';

// For charting the emotion timeline
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
        console.warn("No interviewId in location.state - can't fetch analysis");
        return;
      }
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

  // Build the chart data once we have emotionTimeline
  useEffect(() => {
    if (analysisData && analysisData.emotionTimeline) {
      const timeline = analysisData.emotionTimeline; 
      const EMOTIONS_TO_PLOT = ["happy", "neutral", "angry", "surprise"];

      const labels = timeline.map(entry => {
        const t = new Date(entry.timestamp);
        return t.toLocaleTimeString();
      });

      const datasets = EMOTIONS_TO_PLOT.map(emotionKey => {
        const dataPoints = timeline.map(entry => {
          const dist = entry.distribution || {};
          return dist[emotionKey] || 0;
        });
        return {
          label: emotionKey,
          data: dataPoints,
          borderWidth: 2
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
    return <div style={{ textAlign:'center', marginTop:'50px'}}>
      <h2>Loading Analysis...</h2>
      <p>If no data appears, ensure you had an interviewId in the route state.</p>
    </div>;
  }

  const { questions, answers, status, completed_at } = analysisData;

  return (
    <div style={{ textAlign:'center', marginTop:'30px' }}>
      <h2>Interview Analysis</h2>
      <p>Status: {status} {completed_at && `Completed at ${completed_at}`}</p>

      {/* Q & A Display */}
      <div style={{ margin:'20px auto', maxWidth:'600px', textAlign:'left'}}>
        <h3>Questions & Answers</h3>
        {questions.map((q, idx)=> {
          const matchingAns = answers.find(a => a.questionIndex===idx);
          return (
            <div key={idx} style={{ marginBottom:'20px'}}>
              <strong>Q{idx+1}:</strong> {q}
              {matchingAns ? (
                <div style={{ marginLeft:'20px'}}>
                  <p><strong>Transcript:</strong> {matchingAns.transcript}</p>
                  <p><strong>Speech WPM:</strong> {matchingAns.wpm.toFixed(2)}</p>
                  <p><strong>Filler Words Used:</strong> {JSON.stringify(matchingAns.fillerWordsUsed)}</p>
                </div>
              ) : (
                <p style={{ marginLeft:'20px', color:'red'}}>
                  No answer recorded
                </p>
              )}
            </div>
          );
        })}
      </div>

      {/* Emotion Timeline Chart */}
      <div style={{ marginTop:'40px', maxWidth:'800px', margin:'0 auto'}}>
        <h3>Emotion Timeline</h3>
        {emotionChartData ? (
          <Line data={emotionChartData} />
        ) : (
          <p>No emotion data logged.</p>
        )}
      </div>
    </div>
  );
}

export default Analysis;
