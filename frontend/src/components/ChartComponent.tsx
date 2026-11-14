// frontend/src/components/ChartComponent.tsx
import React from 'react';
import { Line } from 'react-chartjs-2';
import 'chart.js/auto';

interface Props { data: any[]; label: string; title: string; }
export default function ChartComponent({ data, label, title }: Props) {
  const chartData = {
    labels: data.map(pt => new Date(pt.date).toLocaleString()),
    datasets: [
      {
        label: label,
        data: data.map(pt => pt.value),
        borderColor: 'rgba(75,192,192,1)',
        backgroundColor: 'rgba(75,192,192,0.2)',
      },
    ]
  };
  const options = { responsive: true, plugins: { title: { display: true, text: title } } };
  return <Line data={chartData} options={options} />;
}
