import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const KPIS = [
  { titulo: "Ingresos del Mes", valor: "$ 0", detalle: "Fase 2" },
  { titulo: "Cuentas por Cobrar", valor: "$ 0", detalle: "Fase 3" },
  { titulo: "Gastos del Mes", valor: "$ 0", detalle: "Fase 2" },
];

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[#2A237A]">Panel de Control</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {KPIS.map((kpi) => (
          <Card key={kpi.titulo}>
            <CardHeader>
              <CardTitle className="text-base text-gray-500">{kpi.titulo}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-[#2A237A]">{kpi.valor}</p>
              <p className="mt-1 text-sm text-gray-400">Se implementará en {kpi.detalle}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
