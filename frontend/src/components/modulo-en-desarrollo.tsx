import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ModuloEnDesarrollo({ titulo, fase }: { titulo: string; fase: string }) {
  return (
    <Card className="mx-auto max-w-xl">
      <CardHeader>
        <CardTitle className="text-lg">{titulo}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-base text-gray-500">
          Este módulo se implementará en la <strong>{fase}</strong> del plan de desarrollo.
        </p>
      </CardContent>
    </Card>
  );
}
