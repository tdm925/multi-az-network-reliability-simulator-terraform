variable "project_name" {
  type    = string
  default = "nrst"
}

variable "region" {
  type    = string
  default = "eu-north-1"
}

variable "aws_profile" {
  type    = string
  default = "nrst-deployer"
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.0.0/24", "10.0.1.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "container_port" {
  type    = number
  default = 80
}

variable "container_image" {
  type    = string
  default = "public.ecr.aws/nginx/nginx:latest"
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "alert_email" {
  type        = string
  description = "Email address for alarm notifications"
}

variable "unhealthy_host_threshold" {
  type    = number
  default = 1
}
