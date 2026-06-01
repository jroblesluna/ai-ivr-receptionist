# ------------------------------------------------------------------------------
# VPC
# ------------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "pickup-${var.environment}-vpc"
  }
}

# ------------------------------------------------------------------------------
# Internet Gateway
# ------------------------------------------------------------------------------

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "pickup-${var.environment}-igw"
  }
}

# ------------------------------------------------------------------------------
# Public Subnets
# ------------------------------------------------------------------------------

resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 1) # 10.0.1.0/24, 10.0.2.0/24
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "pickup-${var.environment}-public-${count.index + 1}"
  }
}

# ------------------------------------------------------------------------------
# Private Subnets
# ------------------------------------------------------------------------------

resource "aws_subnet" "private" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 3) # 10.0.3.0/24, 10.0.4.0/24
  availability_zone = var.azs[count.index]

  tags = {
    Name = "pickup-${var.environment}-private-${count.index + 1}"
  }
}

# ------------------------------------------------------------------------------
# NAT Gateway (single, in first public subnet)
# ------------------------------------------------------------------------------

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "pickup-${var.environment}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name = "pickup-${var.environment}-nat"
  }

  depends_on = [aws_internet_gateway.main]
}

# ------------------------------------------------------------------------------
# Route Tables
# ------------------------------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "pickup-${var.environment}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count = 2

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = {
    Name = "pickup-${var.environment}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count = 2

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ------------------------------------------------------------------------------
# Security Groups
# ------------------------------------------------------------------------------

resource "aws_security_group" "web" {
  name        = "pickup-${var.environment}-sg-web"
  description = "Allow inbound HTTP and HTTPS traffic"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "pickup-${var.environment}-sg-web"
  }
}

resource "aws_security_group" "rds" {
  name        = "pickup-${var.environment}-sg-rds"
  description = "Allow inbound PostgreSQL from web security group only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from web SG"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.web.id]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "pickup-${var.environment}-sg-rds"
  }
}
