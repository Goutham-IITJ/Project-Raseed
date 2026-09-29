"use client";
import { ErrorState } from "@/components/ui";
export default function ErrorPage({ reset }: { reset: () => void }) { return <ErrorState message="This page couldn’t load. Please try again." retry={reset} />; }
