import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend, BarChart, Bar, XAxis, YAxis } from "recharts";
import { Globe, Cpu, Monitor } from "lucide-react";

export default function NvidiaRevenueDashboard() {
  const COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#6366f1"];

  const revenueStreams = [
    { name: "Compute & Networking", value: 89 },
    { name: "Graphics", value: 11 }
  ];

  const regionalRevenue = [
    { region: "United States", value: 46 },
    { region: "Singapore", value: 18 },
    { region: "Taiwan", value: 15 },
    { region: "China", value: 13 },
    { region: "Other (incl. EU)", value: 6 }
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 p-6">
      {/* Revenue Streams */}
      <Card className="shadow-lg rounded-2xl">
        <CardHeader className="flex items-center gap-2">
          <Cpu className="text-emerald-500" />
          <CardTitle>Revenue Streams (Q2 FY2026)</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={revenueStreams} cx="50%" cy="50%" labelLine={false} label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`} outerRadius={100} dataKey="value">
                {revenueStreams.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
          <p className="text-sm text-gray-500 mt-2">
            Compute & Networking drives nearly 90% of NVIDIA’s revenue, led by data centers, automotive, and DGX Cloud.
          </p>
        </CardContent>
      </Card>

      {/* Revenue by Region */}
      <Card className="shadow-lg rounded-2xl">
        <CardHeader className="flex items-center gap-2">
          <Globe className="text-blue-500" />
          <CardTitle>Revenue by Country</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={regionalRevenue}>
              <XAxis dataKey="region" tick={{ fontSize: 12 }} interval={0} angle={-20} dy={10} />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="value" fill="#3b82f6" radius={[8, 8, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <p className="text-sm text-gray-500 mt-2">
            U.S. remains the dominant source (46%) followed by Singapore (18%) and Taiwan (15%). China contributes 13%, while Europe is under 6% despite growing AI infrastructure projects.
          </p>
        </CardContent>
      </Card>

      {/* Narrative Section */}
      <Card className="col-span-1 lg:col-span-2 shadow-lg rounded-2xl">
        <CardHeader className="flex items-center gap-2">
          <Monitor className="text-indigo-500" />
          <CardTitle>Market Outlook & Risks</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-gray-700 leading-relaxed">
            NVIDIA projects next-quarter revenue of <strong>$54 billion ± 2%</strong>, excluding any H20 chip shipments to China. Despite export restrictions, the company is expanding AI infrastructure collaborations with <strong>France, Germany, Italy, Spain, and the U.K.</strong> to build the world’s first <strong>industrial AI cloud</strong> for European manufacturing.
          </p>
          <p className="text-gray-700 leading-relaxed mt-3">
            CEO Jensen Huang noted, “<em>China is nanoseconds behind America in AI. It’s vital that America wins by racing ahead and winning developers worldwide.</em>” Still, NVIDIA estimates up to <strong>$15 billion</strong> in lost sales due to China export controls. China remains the company’s <strong>4th-largest market (~$17 billion in FY2025)</strong>, underscoring significant geopolitical risk.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
