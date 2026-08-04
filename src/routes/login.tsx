import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { Mail, Lock, IdCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  PixelClouds,
  PixelParticles,
  PixelSkyline,
  PixelMascot,
  PixelDivider,
} from "@/components/pixel/pixel-art";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in to ORION — IIIT Kottayam" },
      { name: "description", content: "Sign in to ORION with your IIIT Kottayam email, student ID or Google account." },
      { property: "og:title", content: "Sign in to ORION" },
      { property: "og:description", content: "Access your IIIT Kottayam campus workspace." },
    ],
  }),
  component: LoginPage,
});

const schema = z.object({
  email: z.string().email("Enter a valid campus email"),
  password: z.string().min(6, "At least 6 characters"),
  remember: z.boolean().optional(),
});

function LoginPage() {
  const navigate = useNavigate();
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { email: "aarav.menon@iiitkottayam.ac.in", password: "orion2026", remember: true },
  });

  function onSubmit() {
    toast.success("Welcome back to ORION");
    navigate({ to: "/role" });
  }

  return (
    <div className="relative grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-10">
        <div className="absolute inset-0 gradient-campus opacity-95" />
        <PixelClouds />
        <PixelParticles count={20} />
        <div className="relative z-10">
          <p className="font-pixel text-sm text-primary-foreground">ORION</p>
          <p className="mt-2 font-mono text-[11px] tracking-widest text-primary-foreground/80 uppercase">
            IIIT Kottayam
          </p>
        </div>
        <div className="relative z-10 max-w-sm">
          <h2 className="text-3xl font-bold tracking-tight text-primary-foreground">
            Your intelligent campus assistant.
          </h2>
          <p className="mt-3 text-sm text-primary-foreground/85">
            Timetables, attendance, mess menus, faculty hours, clubs and AI answers — one calm workspace for the whole
            campus.
          </p>
          <PixelDivider className="mt-6 opacity-60" />
        </div>
        <div className="relative z-10 opacity-90">
          <PixelSkyline />
        </div>
      </div>

      <div className="flex items-center justify-center px-5 py-12">
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-sm"
        >
          <div className="flex items-center gap-3 lg:hidden">
            <PixelMascot size={4} />
            <span className="font-pixel text-xs text-primary">ORION</span>
          </div>
          <h1 className="mt-6 text-2xl font-bold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-muted-foreground">Use your campus credentials to continue.</p>

          <Tabs defaultValue="email" className="mt-6">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="email">Email</TabsTrigger>
              <TabsTrigger value="sid">Student ID</TabsTrigger>
            </TabsList>

            <TabsContent value="email">
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4 pt-4">
                <div className="space-y-1.5">
                  <Label htmlFor="email">Campus email</Label>
                  <div className="relative">
                    <Mail className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input id="email" className="pl-9" {...form.register("email")} />
                  </div>
                  {form.formState.errors.email && (
                    <p className="text-xs text-destructive">{form.formState.errors.email.message}</p>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Lock className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input id="password" type="password" className="pl-9" {...form.register("password")} />
                  </div>
                  {form.formState.errors.password && (
                    <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>
                  )}
                </div>
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Checkbox defaultChecked /> Remember me
                  </label>
                  <button type="button" className="text-xs font-medium text-primary hover:underline">
                    Forgot password?
                  </button>
                </div>
                <Button type="submit" className="w-full">
                  Continue
                </Button>
              </form>
            </TabsContent>

            <TabsContent value="sid">
              <div className="space-y-4 pt-4">
                <div className="space-y-1.5">
                  <Label htmlFor="sid">Student ID</Label>
                  <div className="relative">
                    <IdCard className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                    <Input id="sid" className="pl-9 font-mono" placeholder="2022BCS0142" />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="sid-pass">Password</Label>
                  <Input id="sid-pass" type="password" placeholder="••••••••" />
                </div>
                <Button className="w-full" onClick={() => navigate({ to: "/role" })}>
                  Continue
                </Button>
              </div>
            </TabsContent>
          </Tabs>

          <div className="my-5 flex items-center gap-3">
            <span className="h-px flex-1 bg-border" />
            <span className="font-mono text-[10px] tracking-widest text-muted-foreground uppercase">or</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <Button variant="outline" className="w-full" onClick={() => navigate({ to: "/role" })}>
            Continue with Google
          </Button>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            New here?{" "}
            <Link to="/onboarding" className="font-medium text-primary hover:underline">
              Take the tour
            </Link>
          </p>
        </motion.div>
      </div>
    </div>
  );
}
